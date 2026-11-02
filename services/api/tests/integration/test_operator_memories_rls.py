"""Integration: metadata-only operator memory reads honor tenant scope and 404."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

import pytest
from apierror_py import NOT_FOUND
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.db import session_with_org
from app.errors import ApiError
from app.services.operator_memories import (
    ListMemoriesArgs,
    MemoryListFilters,
    get_operator_memory,
    list_operator_memories,
)

pytestmark = pytest.mark.integration

START = datetime(2026, 11, 2, 8, tzinfo=UTC)


async def _seed_org(session: AsyncSession, org_id: UUID, name: str) -> None:
    await session.execute(
        text(
            "INSERT INTO ibex_core.organizations (id, name, slug) "
            "VALUES (CAST(:id AS uuid), :name, :slug)"
        ),
        {"id": str(org_id), "name": name, "slug": f"mem-rls-{org_id.hex}"},
    )


async def _seed_agent(session: AsyncSession, org_id: UUID, agent_id: UUID, name: str) -> None:
    await session.execute(
        text(
            "INSERT INTO ibex_core.agents (id, org_id, name, slug, status) "
            "VALUES (CAST(:id AS uuid), CAST(:org_id AS uuid), :name, :slug, 'active')"
        ),
        {
            "id": str(agent_id),
            "org_id": str(org_id),
            "name": name,
            "slug": f"mem-rls-{agent_id.hex}",
        },
    )


@dataclass(frozen=True)
class SeedMemory:
    org_id: UUID
    agent_id: UUID
    memory_id: UUID
    content: str
    category: str = "factual"
    status: str = "active"
    created_at: datetime = START
    metadata: str = '{"visibility":"agent","pinned":false,"tags":["support"]}'


async def _seed_memory(session: AsyncSession, seed: SeedMemory) -> None:
    await session.execute(
        text(
            """
            INSERT INTO ibex_core.memories (
              id, org_id, agent_id, content, content_hash, content_tokens,
              category, status, confidence, usefulness_score, source,
              retrieval_count, pii_detected, pii_redacted, metadata,
              valid_from, observed_at, created_at, updated_at
            ) VALUES (
              CAST(:id AS uuid), CAST(:org_id AS uuid), CAST(:agent_id AS uuid),
              :content, :content_hash, 7, :category, :status, 0.80, 0.50,
              'extracted', 2, FALSE, FALSE,
              CAST(:metadata AS jsonb),
              :created_at, :created_at, :created_at, :created_at
            )
            """
        ),
        {
            "id": str(seed.memory_id),
            "org_id": str(seed.org_id),
            "agent_id": str(seed.agent_id),
            "content": seed.content,
            "content_hash": f"hash-{seed.memory_id.hex}",
            "category": seed.category,
            "status": seed.status,
            "created_at": seed.created_at,
            "metadata": seed.metadata,
        },
    )


async def _cleanup(
    session_factory: async_sessionmaker[AsyncSession], org_a: UUID, org_b: UUID
) -> None:
    async with session_factory() as cleanup, cleanup.begin():
        await cleanup.execute(
            text(
                "DELETE FROM ibex_core.memories "
                "WHERE org_id IN (CAST(:a AS uuid), CAST(:b AS uuid))"
            ),
            {"a": str(org_a), "b": str(org_b)},
        )
        await cleanup.execute(
            text(
                "DELETE FROM ibex_core.agents "
                "WHERE org_id IN (CAST(:a AS uuid), CAST(:b AS uuid))"
            ),
            {"a": str(org_a), "b": str(org_b)},
        )
        await cleanup.execute(
            text(
                "DELETE FROM ibex_core.organizations "
                "WHERE id IN (CAST(:a AS uuid), CAST(:b AS uuid))"
            ),
            {"a": str(org_a), "b": str(org_b)},
        )


@dataclass(frozen=True)
class SeedIds:
    org_a: UUID
    org_b: UUID
    agent_a: UUID
    agent_b: UUID
    memory_a1: UUID
    memory_a2: UUID
    memory_b: UUID
    memory_malformed: UUID


async def _seed_fixture(
    session_factory: async_sessionmaker[AsyncSession], ids: SeedIds
) -> None:
    async with session_factory() as admin, admin.begin():
        await admin.execute(
            text("SELECT set_config('app.is_service_account', 'true', true)")
        )
        await _seed_org(admin, ids.org_a, "Memory RLS A")
        await _seed_org(admin, ids.org_b, "Memory RLS B")
        await _seed_agent(admin, ids.org_a, ids.agent_a, "Agent A")
        await _seed_agent(admin, ids.org_b, ids.agent_b, "Agent B")
        await _seed_memory(
            admin,
            SeedMemory(ids.org_a, ids.agent_a, ids.memory_a1, "A one", created_at=START),
        )
        await _seed_memory(
            admin,
            SeedMemory(
                ids.org_a,
                ids.agent_a,
                ids.memory_a2,
                "A two",
                status="archived",
                created_at=START + timedelta(minutes=1),
            ),
        )
        await _seed_memory(
            admin,
            SeedMemory(
                ids.org_a,
                ids.agent_a,
                ids.memory_malformed,
                "A malformed metadata",
                created_at=START - timedelta(minutes=1),
                metadata='{"visibility":"public","pinned":"yes","tags":"not-an-array"}',
            ),
        )
        await _seed_memory(
            admin, SeedMemory(ids.org_b, ids.agent_b, ids.memory_b, "B one")
        )


async def _assert_projection(session: AsyncSession, ids: SeedIds) -> None:
    listed = await list_operator_memories(
        session,
        ListMemoriesArgs(
            org_id=ids.org_a,
            cursor=None,
            limit=50,
            filters=MemoryListFilters(),
        ),
    )
    assert [item.id for item in listed.data] == [
        ids.memory_a2,
        ids.memory_a1,
        ids.memory_malformed,
    ]
    dumped = listed.data[0].model_dump()
    assert "content" not in dumped
    assert "content_hash" not in dumped
    assert "embedding" not in dumped
    assert "metadata" not in dumped
    assert dumped["tags"] == ["support"]

    malformed = next(item for item in listed.data if item.id == ids.memory_malformed)
    assert malformed.visibility == "agent"
    assert malformed.pinned is False
    assert malformed.tags == []

    detail = await get_operator_memory(session, ids.org_a, ids.memory_a1)
    assert detail.id == ids.memory_a1
    with pytest.raises(ApiError) as err:
        await get_operator_memory(session, ids.org_a, ids.memory_b)
    assert err.value.code == NOT_FOUND


async def _assert_status_filter(session: AsyncSession, ids: SeedIds) -> None:
    archived = await list_operator_memories(
        session,
        ListMemoriesArgs(
            org_id=ids.org_a,
            cursor=None,
            limit=50,
            filters=MemoryListFilters(status="archived"),
        ),
    )
    assert [item.id for item in archived.data] == [ids.memory_a2]


async def _assert_cursor(session: AsyncSession, ids: SeedIds) -> None:
    first = await list_operator_memories(
        session,
        ListMemoriesArgs(
            org_id=ids.org_a,
            cursor=None,
            limit=1,
            filters=MemoryListFilters(),
        ),
    )
    assert first.pagination.has_more is True
    assert first.pagination.next_cursor is not None
    second = await list_operator_memories(
        session,
        ListMemoriesArgs(
            org_id=ids.org_a,
            cursor=first.pagination.next_cursor,
            limit=1,
            filters=MemoryListFilters(),
        ),
    )
    assert [item.id for item in second.data] == [ids.memory_a1]


async def _supersede(
    session: AsyncSession,
    org_id: UUID,
    older: UUID,
    newer: UUID,
) -> None:
    """Record "`newer` supersedes `older`": the newer memory is the edge source."""
    await session.execute(
        text(
            "INSERT INTO ibex_core.memory_relationships ("
            "org_id, source_memory_id, target_memory_id, relationship_type, confidence"
            ") VALUES (CAST(:org_id AS uuid), CAST(:newer AS uuid), CAST(:older AS uuid), "
            "'supersedes', 0.9)"
        ),
        {"org_id": str(org_id), "older": str(older), "newer": str(newer)},
    )
    await session.execute(
        text(
            "UPDATE ibex_core.memories SET superseded_by = CAST(:newer AS uuid), "
            "status = 'superseded' WHERE id = CAST(:older AS uuid) "
            "AND org_id = CAST(:org_id AS uuid)"
        ),
        {"older": str(older), "newer": str(newer), "org_id": str(org_id)},
    )


@pytest.mark.asyncio
async def test_memory_lineage_is_tenant_scoped_and_resolves_the_tip(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    ids = SeedIds(
        org_a=uuid4(),
        org_b=uuid4(),
        agent_a=uuid4(),
        agent_b=uuid4(),
        memory_a1=uuid4(),
        memory_a2=uuid4(),
        memory_b=uuid4(),
        memory_malformed=uuid4(),
    )
    try:
        await _seed_fixture(session_factory, ids)
        async with session_factory() as admin, admin.begin():
            await admin.execute(text("SELECT set_config('app.is_service_account', 'true', true)"))
            # A supersedes A1 -> A2, and B supersedes nothing in org A.
            # The newer memory is the `source` of `supersedes`; the older one is the target.
            await _supersede(admin, ids.org_a, ids.memory_a1, ids.memory_a2)

        async with session_with_org(session_factory, str(ids.org_a)) as session:
            detail = await get_operator_memory(session, ids.org_a, ids.memory_a1)

        assert detail.lineage.superseded_by is not None
        assert detail.lineage.superseded_by.id == ids.memory_a2
        assert detail.lineage.superseded_by.tombstoned is False
        assert detail.lineage.tip is not None
        assert detail.lineage.tip.id == ids.memory_a2
        assert [edge.memory_id for edge in detail.lineage.replaced_by] == [ids.memory_a2]
        assert detail.lineage.replaced_by[0].relationship_type == "supersedes"
        # The replacement is the fixture's archived memory; the edge reports its state.
        assert detail.lineage.replaced_by[0].status == "archived"
        assert detail.lineage.replaces == []

        async with session_with_org(session_factory, str(ids.org_b)) as session:
            other = await get_operator_memory(session, ids.org_b, ids.memory_b)
            with pytest.raises(ApiError) as err:
                await get_operator_memory(session, ids.org_b, ids.memory_a1)

        assert other.lineage.replaced_by == []
        # No successor: the memory is its own chain head.
        assert other.lineage.tip is not None
        assert other.lineage.tip.id == ids.memory_b
        assert err.value.code == NOT_FOUND
    finally:
        await _cleanup(session_factory, ids.org_a, ids.org_b)


@pytest.mark.asyncio
async def test_operator_memories_are_tenant_scoped_and_exclude_content(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    ids = SeedIds(
        org_a=uuid4(),
        org_b=uuid4(),
        agent_a=uuid4(),
        agent_b=uuid4(),
        memory_a1=uuid4(),
        memory_a2=uuid4(),
        memory_b=uuid4(),
        memory_malformed=uuid4(),
    )
    try:
        await _seed_fixture(session_factory, ids)
        async with session_with_org(session_factory, str(ids.org_a)) as session:
            await _assert_projection(session, ids)
            await _assert_status_filter(session, ids)
            await _assert_cursor(session, ids)
    finally:
        await _cleanup(session_factory, ids.org_a, ids.org_b)
