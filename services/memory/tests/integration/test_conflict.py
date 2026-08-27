"""Integration: supersession persist + relationship row (org-scoped)."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from uuid import UUID, uuid4

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.conflict.persist import (
    CandidateLoad,
    RelationshipInsert,
    apply_supersession,
    insert_relationship,
    load_candidate_memories,
)
from app.conflict.types import SupersedeApply
from app.dedup.hash import content_hash_sha256
from tests.integration.conftest import seed_org_agent_memory

pytestmark = pytest.mark.integration


@dataclass(frozen=True, slots=True)
class _MemorySeed:
    org_id: UUID
    agent_id: UUID
    content: str
    valid_from: datetime
    valid_until: datetime | None = None


async def _set_service_org(session: AsyncSession, org_id: UUID) -> None:
    await session.execute(
        text(  # nosemgrep: python.sqlalchemy.security.audit.avoid-sqlalchemy-text.avoid-sqlalchemy-text
            "SELECT set_config('app.is_service_account', 'true', true)"
        )
    )
    await session.execute(
        text(  # nosemgrep: python.sqlalchemy.security.audit.avoid-sqlalchemy-text.avoid-sqlalchemy-text
            "SELECT set_config('app.current_org_id', :org_id, true)"
        ),
        {"org_id": str(org_id)},
    )


async def _insert_memory(
    factory: async_sessionmaker[AsyncSession],
    seed: _MemorySeed,
) -> UUID:
    memory_id = uuid4()
    async with factory() as session, session.begin():
        await session.execute(
            text(  # nosemgrep: python.sqlalchemy.security.audit.avoid-sqlalchemy-text.avoid-sqlalchemy-text
                "SELECT set_config('app.is_service_account', 'true', true)"
            )
        )
        await session.execute(
            text(  # nosemgrep: python.sqlalchemy.security.audit.avoid-sqlalchemy-text.avoid-sqlalchemy-text
                """
                INSERT INTO ibex_core.memories (
                    id, org_id, agent_id, content, content_hash, content_tokens,
                    valid_from, valid_until
                ) VALUES (
                    :id, :org, :agent, :content, :hash, :tokens, :vf, :vu
                )
                """
            ),
            {
                "id": str(memory_id),
                "org": str(seed.org_id),
                "agent": str(seed.agent_id),
                "content": seed.content,
                "hash": content_hash_sha256(seed.content),
                "tokens": max(1, len(seed.content.split())),
                "vf": seed.valid_from,
                "vu": seed.valid_until,
            },
        )
    return memory_id


async def _fetch_supersession_state(
    factory: async_sessionmaker[AsyncSession],
    *,
    org_id: UUID,
    old_id: UUID,
    new_id: UUID,
) -> tuple[str, str, str]:
    async with factory() as session:
        await _set_service_org(session, org_id)
        row = (
            await session.execute(
                text(  # nosemgrep: python.sqlalchemy.security.audit.avoid-sqlalchemy-text.avoid-sqlalchemy-text
                    """
                    SELECT status, superseded_by::text AS tip
                    FROM ibex_core.memories
                    WHERE id = :id AND org_id = :org
                    """
                ),
                {"id": str(old_id), "org": str(org_id)},
            )
        ).one()
        edge = (
            await session.execute(
                text(  # nosemgrep: python.sqlalchemy.security.audit.avoid-sqlalchemy-text.avoid-sqlalchemy-text
                    """
                    SELECT relationship_type
                    FROM ibex_core.memory_relationships
                    WHERE org_id = :org
                      AND source_memory_id = :src
                      AND target_memory_id = :tgt
                    """
                ),
                {"org": str(org_id), "src": str(new_id), "tgt": str(old_id)},
            )
        ).scalar_one()
    return str(row.status), str(row.tip), str(edge)


@pytest.mark.asyncio
async def test_apply_supersession_updates_status_and_edge(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    org_id, agent_id, _seed = await seed_org_agent_memory(
        session_factory, content="seed"
    )
    march = datetime(2026, 3, 1, tzinfo=UTC)
    june = datetime(2026, 6, 1, tzinfo=UTC)
    old_id = await _insert_memory(
        session_factory,
        _MemorySeed(
            org_id=org_id,
            agent_id=agent_id,
            content="User prefers Python",
            valid_from=march,
            valid_until=june,
        ),
    )
    new_id = await _insert_memory(
        session_factory,
        _MemorySeed(
            org_id=org_id,
            agent_id=agent_id,
            content="User is switching to Go",
            valid_from=june,
        ),
    )
    loaded = await load_candidate_memories(
        session_factory, CandidateLoad(org_id=org_id, memory_ids=(old_id,))
    )
    assert len(loaded) == 1
    await apply_supersession(
        session_factory,
        SupersedeApply(
            org_id=org_id,
            new_memory_id=new_id,
            target_memory_id=old_id,
            closed_at=june,
        ),
    )
    status, tip, edge = await _fetch_supersession_state(
        session_factory, org_id=org_id, old_id=old_id, new_id=new_id
    )
    assert status == "superseded"
    assert tip == str(new_id)
    assert edge == "supersedes"


@pytest.mark.asyncio
async def test_load_candidates_cross_tenant_empty(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    _org_a, _, mem_a = await seed_org_agent_memory(session_factory, content="a")
    org_b, _, _ = await seed_org_agent_memory(session_factory, content="b")
    loaded = await load_candidate_memories(
        session_factory, CandidateLoad(org_id=org_b, memory_ids=(mem_a,))
    )
    assert loaded == []


@pytest.mark.asyncio
async def test_insert_contradicts_relationship(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    org_id, agent_id, left = await seed_org_agent_memory(session_factory, content="left")
    right = await _insert_memory(
        session_factory,
        _MemorySeed(
            org_id=org_id,
            agent_id=agent_id,
            content="right",
            valid_from=datetime(2026, 1, 1, tzinfo=UTC),
        ),
    )
    await insert_relationship(
        session_factory,
        RelationshipInsert(
            org_id=org_id,
            source_memory_id=left,
            target_memory_id=right,
            relationship_type="contradicts",
            resolution_notes="overlap fixture",
        ),
    )
    async with session_factory() as session:
        await _set_service_org(session, org_id)
        rel = (
            await session.execute(
                text(  # nosemgrep: python.sqlalchemy.security.audit.avoid-sqlalchemy-text.avoid-sqlalchemy-text
                    """
                    SELECT relationship_type FROM ibex_core.memory_relationships
                    WHERE org_id = :org AND source_memory_id = :s AND target_memory_id = :t
                    """
                ),
                {"org": str(org_id), "s": str(left), "t": str(right)},
            )
        ).scalar_one()
    assert rel == "contradicts"
