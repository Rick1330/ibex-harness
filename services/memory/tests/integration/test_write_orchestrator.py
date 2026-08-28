"""Integration tests for MemoryWriteOrchestrator (steps 7–9 DB persist)."""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime
from uuid import uuid4

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.config import Settings
from app.dedup.hash import content_hash_sha256
from app.exceptions import DuplicateMemoryError
from app.write.models import CreateMemoryCommand, WriteOutcomeKind
from tests.integration.conftest import fetch_memory_field, seed_org_agent_memory, with_service_org
from tests.integration.write_orchestrator_support import (
    QuarantinePii,
    build_orchestrator,
    ensure_pii_ready,
    seed_vector_memory,
    set_content_hash,
)

pytestmark = pytest.mark.integration


@pytest.mark.asyncio
async def test_orchestrator_novel_write_persists_row(
    session_factory: async_sessionmaker[AsyncSession],
    settings: Settings,
    store,
) -> None:
    org_id, agent_id, _ = await seed_org_agent_memory(
        session_factory, content="unrelated seed row"
    )
    orch = build_orchestrator(session_factory, settings, store)
    await ensure_pii_ready(orch)
    outcome = await orch.create(
        CreateMemoryCommand(
            org_id=org_id,
            agent_id=agent_id,
            content="User prefers dark mode dashboards for focus",
            valid_from=datetime(2026, 6, 1, tzinfo=UTC),
        )
    )
    assert outcome.kind == WriteOutcomeKind.CREATED
    assert (
        await fetch_memory_field(
            session_factory,
            org_id=org_id,
            memory_id=outcome.memory.id,
            field="status",
        )
        == "active"
    )


@pytest.mark.asyncio
async def test_orchestrator_exact_duplicate_raises_409_path(
    session_factory: async_sessionmaker[AsyncSession],
    settings: Settings,
    store,
) -> None:
    content = "Exact duplicate orchestrator payload"
    org_id, agent_id, memory_id = await seed_org_agent_memory(
        session_factory, content=content
    )
    await set_content_hash(
        session_factory,
        org_id=org_id,
        memory_id=memory_id,
        content_hash=content_hash_sha256(content),
    )
    orch = build_orchestrator(session_factory, settings, store)
    await ensure_pii_ready(orch)
    with pytest.raises(DuplicateMemoryError) as exc_info:
        await orch.create(
            CreateMemoryCommand(org_id=org_id, agent_id=agent_id, content=content)
        )
    assert exc_info.value.existing_id == memory_id


@pytest.mark.asyncio
async def test_orchestrator_concurrent_identical_content_race(
    session_factory: async_sessionmaker[AsyncSession],
    settings: Settings,
    store,
) -> None:
    content = f"race payload {uuid4().hex}"
    org_id, agent_id, _ = await seed_org_agent_memory(
        session_factory, content="race seed unrelated"
    )
    orch = build_orchestrator(session_factory, settings, store)
    await ensure_pii_ready(orch)
    cmd = CreateMemoryCommand(org_id=org_id, agent_id=agent_id, content=content)
    results = await asyncio.gather(
        orch.create(cmd),
        orch.create(cmd),
        return_exceptions=True,
    )
    successes = [r for r in results if not isinstance(r, BaseException)]
    failures = [r for r in results if isinstance(r, BaseException)]
    assert len(successes) == 1
    assert len(failures) == 1
    assert isinstance(failures[0], DuplicateMemoryError)


@pytest.mark.asyncio
async def test_orchestrator_quarantine_persists_quarantined_row(
    session_factory: async_sessionmaker[AsyncSession],
    settings: Settings,
    store,
) -> None:
    org_id, agent_id, _ = await seed_org_agent_memory(
        session_factory, content="quarantine seed"
    )
    orch = build_orchestrator(session_factory, settings, store, pii=QuarantinePii())
    outcome = await orch.create(
        CreateMemoryCommand(org_id=org_id, agent_id=agent_id, content="Contact Jordan")
    )
    assert outcome.kind == WriteOutcomeKind.QUARANTINED
    assert (
        await fetch_memory_field(
            session_factory,
            org_id=org_id,
            memory_id=outcome.memory.id,
            field="status",
        )
        == "quarantined"
    )


@pytest.mark.asyncio
async def test_orchestrator_supersession_in_one_transaction(
    session_factory: async_sessionmaker[AsyncSession],
    settings: Settings,
    store,
) -> None:
    org_id, agent_id, _ = await seed_org_agent_memory(
        session_factory, content="supersede seed"
    )
    march = datetime(2026, 3, 1, tzinfo=UTC)
    june = datetime(2026, 6, 1, tzinfo=UTC)
    old_content = "User prefers Python for all backend services"
    old_id, vec = await seed_vector_memory(
        session_factory,
        store,
        org_id=org_id,
        agent_id=agent_id,
        content=old_content,
        valid_from=march,
        valid_until=june,
    )

    async def embed(_text: str) -> list[float]:
        return list(vec)

    orch = build_orchestrator(session_factory, settings, store, embed=embed)
    await ensure_pii_ready(orch)
    outcome = await orch.create(
        CreateMemoryCommand(
            org_id=org_id,
            agent_id=agent_id,
            content="User is switching to Go for all backend services",
            valid_from=june,
        )
    )
    assert outcome.kind == WriteOutcomeKind.CREATED
    assert (
        await fetch_memory_field(
            session_factory, org_id=org_id, memory_id=old_id, field="status"
        )
        == "superseded"
    )
    assert (
        await fetch_memory_field(
            session_factory, org_id=org_id, memory_id=old_id, field="valid_until"
        )
        == june
    )


@pytest.mark.asyncio
async def test_orchestrator_escalation_row_persisted(
    session_factory: async_sessionmaker[AsyncSession],
    settings: Settings,
    store,
) -> None:
    org_id, agent_id, _ = await seed_org_agent_memory(
        session_factory, content="escalation seed"
    )
    overlap_start = datetime(2026, 1, 1, tzinfo=UTC)
    overlap_end = datetime(2026, 12, 31, tzinfo=UTC)
    old_content = "User office is in Berlin Germany"
    old_id, vec = await seed_vector_memory(
        session_factory,
        store,
        org_id=org_id,
        agent_id=agent_id,
        content=old_content,
        valid_from=overlap_start,
        valid_until=overlap_end,
        hotspot=7,
    )

    async def embed(_text: str) -> list[float]:
        return list(vec)

    orch = build_orchestrator(session_factory, settings, store, embed=embed)
    await ensure_pii_ready(orch)
    outcome = await orch.create(
        CreateMemoryCommand(
            org_id=org_id,
            agent_id=agent_id,
            content="User office is in Munich Germany",
            valid_from=datetime(2026, 6, 1, tzinfo=UTC),
            valid_until=overlap_end,
        )
    )
    assert outcome.kind == WriteOutcomeKind.CREATED
    async with session_factory() as session:
        await with_service_org(session, org_id)
        count = (
            await session.execute(
                text(
                    """
                    SELECT COUNT(*)::int AS c
                    FROM ibex_core.memory_conflict_escalations
                    WHERE org_id = :org AND new_memory_id = :new_id
                      AND candidate_memory_id = :candidate
                      AND status = 'pending'
                    """
                ),
                {
                    "org": str(org_id),
                    "new_id": str(outcome.memory.id),
                    "candidate": str(old_id),
                },
            )
        ).one()
    assert int(count.c) == 1


@pytest.mark.asyncio
async def test_orchestrator_cross_tenant_isolated(
    session_factory: async_sessionmaker[AsyncSession],
    settings: Settings,
    store,
) -> None:
    content = "Shared preference text across tenants"
    org_a, agent_a, _ = await seed_org_agent_memory(session_factory, content="seed a")
    org_b, agent_b, _ = await seed_org_agent_memory(session_factory, content="seed b")
    orch_a = build_orchestrator(session_factory, settings, store)
    orch_b = build_orchestrator(session_factory, settings, store)
    await ensure_pii_ready(orch_a)
    await ensure_pii_ready(orch_b)
    out_a = await orch_a.create(
        CreateMemoryCommand(org_id=org_a, agent_id=agent_a, content=content)
    )
    out_b = await orch_b.create(
        CreateMemoryCommand(org_id=org_b, agent_id=agent_b, content=content)
    )
    assert out_a.memory.id != out_b.memory.id

    from app.conflict.persist import CandidateLoad, load_candidate_memories

    cross_loaded = await load_candidate_memories(
        session_factory,
        CandidateLoad(org_id=org_b, memory_ids=(out_a.memory.id,)),
    )
    assert cross_loaded == []
