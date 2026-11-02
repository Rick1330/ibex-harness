"""Integration: metadata-only operator memory reads honor tenant scope and 404."""

from __future__ import annotations

import os
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

import pytest
from apierror_py import NOT_FOUND
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.config import Settings
from app.db import create_engine, create_session_factory, session_with_org
from app.errors import ApiError
from app.services.operator_memories import (
    ListMemoriesArgs,
    MemoryListFilters,
    get_operator_memory,
    list_operator_memories,
)

pytestmark = pytest.mark.integration

CURSOR_SECRET = "cursor-secret-32-bytes-minimum!!"
START = datetime(2026, 11, 2, 8, tzinfo=UTC)


def _require_dsn() -> str:
    dsn = os.environ.get("IBEX_API_DATABASE_URL") or os.environ.get("POSTGRES_TEST_DSN")
    if not dsn:
        pytest.skip("IBEX_API_DATABASE_URL or POSTGRES_TEST_DSN not set")
    return dsn


@pytest.fixture
async def session_factory() -> async_sessionmaker[AsyncSession]:
    engine = create_engine(
        Settings(database_url=_require_dsn(), operator_cursor_secret=CURSOR_SECRET)
    )
    factory = create_session_factory(engine)
    try:
        yield factory
    finally:
        await engine.dispose()


def _settings() -> Settings:
    return Settings(database_url=_require_dsn(), operator_cursor_secret=CURSOR_SECRET)


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
            "metadata": '{"visibility":"agent","pinned":false,"tags":["support"]}',
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
    assert [item.id for item in listed.data] == [ids.memory_a2, ids.memory_a1]
    dumped = listed.data[0].model_dump()
    assert "content" not in dumped
    assert "content_hash" not in dumped
    assert "embedding" not in dumped
    assert "metadata" not in dumped
    assert dumped["tags"] == ["support"]

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
    )
    try:
        await _seed_fixture(session_factory, ids)
        async with session_with_org(session_factory, str(ids.org_a)) as session:
            await _assert_projection(session, ids)
            await _assert_status_filter(session, ids)
            await _assert_cursor(session, ids)
    finally:
        await _cleanup(session_factory, ids.org_a, ids.org_b)
