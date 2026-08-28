"""Integration tests for MemoryWriteOrchestrator (steps 7–9 DB persist)."""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime
from uuid import UUID, uuid4

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.config import Settings
from app.conflict.service import ConflictService
from app.dedup.hash import content_hash_sha256
from app.exceptions import DuplicateMemoryError
from app.pii.types import PiiFinding, PiiProcessResult
from app.vectorstore.base import UpsertRequest
from app.write.models import CreateMemoryCommand, WriteOutcomeKind
from tests.integration.conftest import seed_org_agent_memory, zero_embedding

pytestmark = pytest.mark.integration


class _EmbedProbe:
    def __init__(self) -> None:
        self.seen: list[str] = []

    async def __call__(self, payload: str) -> list[float]:
        self.seen.append(payload)
        return zero_embedding(hotspot=3)


class _QuarantinePii:
    async def process_async(self, content: str) -> PiiProcessResult:
        return PiiProcessResult(
            findings=[PiiFinding("PERSON", 0, min(6, len(content)), 0.40)],
            content=content,
            pii_detected=True,
            pii_redacted=False,
            status="quarantined",
            quarantine_reason="pii_low_confidence",
        )


def _orchestrator(
    session_factory: async_sessionmaker[AsyncSession],
    settings: Settings,
    store,
    *,
    embed=None,
    pii=None,
    subject_extractor=lambda _: "shared-subject-key",
):
    from app.conflict.persist import CandidateLoad, load_candidate_memories
    from app.dedup.persist import (
        ExactHashLookup,
        RetrievalBump,
        find_active_by_content_hash,
        increment_retrieval_count,
    )
    from app.dedup.service import DedupService
    from app.pii.service import PiiService
    from app.pipeline import (
        ConflictStage,
        EmbedStage,
        ExactDedupStage,
        NearDedupStage,
        PiiStage,
        ValidateStage,
        WritePipeline,
    )
    from app.write.orchestrator import MemoryWriteOrchestrator

    probe = embed or _EmbedProbe()
    pii_svc = pii or PiiService(settings)

    async def lookup(o: UUID, a: UUID, h: str) -> UUID | None:
        return await find_active_by_content_hash(
            session_factory, ExactHashLookup(org_id=o, agent_id=a, content_hash=h)
        )

    async def bump(o: UUID, mid: UUID) -> int:
        return await increment_retrieval_count(
            session_factory, RetrievalBump(org_id=o, memory_id=mid)
        )

    dedup = DedupService(
        settings, store=store, exact_lookup=lookup, bump_retrieval=bump
    )
    conflict = ConflictService(settings, subject_extractor=subject_extractor)

    async def load(org_id: UUID, ids: tuple[UUID, ...]):
        return await load_candidate_memories(
            session_factory, CandidateLoad(org_id=org_id, memory_ids=ids)
        )

    pipeline = WritePipeline(
        [
            ValidateStage(settings),
            PiiStage(pii_svc),
            ExactDedupStage(dedup),
            EmbedStage(probe),
            NearDedupStage(dedup),
            ConflictStage(conflict, load_candidates=load, enabled=True),
        ]
    )
    return MemoryWriteOrchestrator(pipeline, session_factory)


async def _set_content_hash(
    factory: async_sessionmaker[AsyncSession],
    *,
    org_id: UUID,
    memory_id: UUID,
    content_hash: str,
) -> None:
    async with factory() as session, session.begin():
        await session.execute(
            text("SELECT set_config('app.is_service_account', 'true', true)")
        )
        await session.execute(
            text("SELECT set_config('app.current_org_id', :org_id, true)"),
            {"org_id": str(org_id)},
        )
        await session.execute(
            text(
                """
                UPDATE ibex_core.memories
                SET content_hash = :hash
                WHERE id = :id AND org_id = :org_id
                """
            ),
            {"hash": content_hash, "id": str(memory_id), "org_id": str(org_id)},
        )


async def _fetch_memory_status(
    factory: async_sessionmaker[AsyncSession], *, org_id: UUID, memory_id: UUID
) -> str:
    async with factory() as session:
        await session.execute(
            text("SELECT set_config('app.is_service_account', 'true', true)")
        )
        await session.execute(
            text("SELECT set_config('app.current_org_id', :org_id, true)"),
            {"org_id": str(org_id)},
        )
        row = (
            await session.execute(
                text(
                    "SELECT status FROM ibex_core.memories WHERE id = :id AND org_id = :org"
                ),
                {"id": str(memory_id), "org": str(org_id)},
            )
        ).one()
    return str(row.status)


@pytest.mark.asyncio
async def test_orchestrator_novel_write_persists_row(
    session_factory: async_sessionmaker[AsyncSession],
    settings: Settings,
    store,
) -> None:
    org_id, agent_id, _ = await seed_org_agent_memory(
        session_factory, content="unrelated seed row"
    )
    orch = _orchestrator(session_factory, settings, store)
    if hasattr(orch._pipeline._stages[1]._pii, "ensure_ready"):
        await orch._pipeline._stages[1]._pii.ensure_ready()
    content = "User prefers dark mode dashboards for focus"
    outcome = await orch.create(
        CreateMemoryCommand(
            org_id=org_id,
            agent_id=agent_id,
            content=content,
            valid_from=datetime(2026, 6, 1, tzinfo=UTC),
        )
    )
    assert outcome.kind == WriteOutcomeKind.CREATED
    status = await _fetch_memory_status(
        session_factory, org_id=org_id, memory_id=outcome.memory.id
    )
    assert status == "active"


@pytest.mark.asyncio
async def test_orchestrator_exact_duplicate_raises_409_path(
    session_factory: async_sessionmaker[AsyncSession],
    settings: Settings,
    store,
) -> None:
    content = "Exact duplicate orchestrator payload"
    digest = content_hash_sha256(content)
    org_id, agent_id, memory_id = await seed_org_agent_memory(
        session_factory, content=content
    )
    await _set_content_hash(
        session_factory, org_id=org_id, memory_id=memory_id, content_hash=digest
    )
    orch = _orchestrator(session_factory, settings, store)
    if hasattr(orch._pipeline._stages[1]._pii, "ensure_ready"):
        await orch._pipeline._stages[1]._pii.ensure_ready()
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
    orch = _orchestrator(session_factory, settings, store)
    if hasattr(orch._pipeline._stages[1]._pii, "ensure_ready"):
        await orch._pipeline._stages[1]._pii.ensure_ready()
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
    orch = _orchestrator(session_factory, settings, store, pii=_QuarantinePii())
    outcome = await orch.create(
        CreateMemoryCommand(org_id=org_id, agent_id=agent_id, content="Contact Jordan")
    )
    assert outcome.kind == WriteOutcomeKind.QUARANTINED
    status = await _fetch_memory_status(
        session_factory, org_id=org_id, memory_id=outcome.memory.id
    )
    assert status == "quarantined"


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
    vec = zero_embedding(hotspot=5)
    old_id = uuid4()
    async with session_factory() as session, session.begin():
        await session.execute(
            text("SELECT set_config('app.is_service_account', 'true', true)")
        )
        await session.execute(
            text("SELECT set_config('app.current_org_id', :org_id, true)"),
            {"org_id": str(org_id)},
        )
        await session.execute(
            text(
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
                "id": str(old_id),
                "org": str(org_id),
                "agent": str(agent_id),
                "content": old_content,
                "hash": content_hash_sha256(old_content),
                "tokens": 5,
                "vf": march,
                "vu": june,
            },
        )
    await store.upsert(
        UpsertRequest(
            memory_id=old_id,
            org_id=org_id,
            embedding=vec,
            embedding_model="test-model",
        )
    )

    async def embed(_text: str) -> list[float]:
        return list(vec)

    orch = _orchestrator(session_factory, settings, store, embed=embed)
    if hasattr(orch._pipeline._stages[1]._pii, "ensure_ready"):
        await orch._pipeline._stages[1]._pii.ensure_ready()
    outcome = await orch.create(
        CreateMemoryCommand(
            org_id=org_id,
            agent_id=agent_id,
            content="User is switching to Go for all backend services",
            valid_from=june,
        )
    )
    assert outcome.kind == WriteOutcomeKind.CREATED
    old_status = await _fetch_memory_status(
        session_factory, org_id=org_id, memory_id=old_id
    )
    assert old_status == "superseded"


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
    vec = zero_embedding(hotspot=7)
    old_id = uuid4()
    async with session_factory() as session, session.begin():
        await session.execute(
            text("SELECT set_config('app.is_service_account', 'true', true)")
        )
        await session.execute(
            text("SELECT set_config('app.current_org_id', :org_id, true)"),
            {"org_id": str(org_id)},
        )
        await session.execute(
            text(
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
                "id": str(old_id),
                "org": str(org_id),
                "agent": str(agent_id),
                "content": old_content,
                "hash": content_hash_sha256(old_content),
                "tokens": 5,
                "vf": overlap_start,
                "vu": overlap_end,
            },
        )
    await store.upsert(
        UpsertRequest(
            memory_id=old_id,
            org_id=org_id,
            embedding=vec,
            embedding_model="test-model",
        )
    )

    async def embed(_text: str) -> list[float]:
        return list(vec)

    orch = _orchestrator(session_factory, settings, store, embed=embed)
    if hasattr(orch._pipeline._stages[1]._pii, "ensure_ready"):
        await orch._pipeline._stages[1]._pii.ensure_ready()
    outcome = await orch.create(
        CreateMemoryCommand(
            org_id=org_id,
            agent_id=agent_id,
            content="User office is in Munich Germany",
            valid_from=datetime(2026, 6, 1, tzinfo=UTC),
            valid_until=datetime(2026, 12, 31, tzinfo=UTC),
        )
    )
    assert outcome.kind == WriteOutcomeKind.CREATED
    async with session_factory() as session:
        await session.execute(
            text("SELECT set_config('app.is_service_account', 'true', true)")
        )
        await session.execute(
            text("SELECT set_config('app.current_org_id', :org_id, true)"),
            {"org_id": str(org_id)},
        )
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
    orch_a = _orchestrator(session_factory, settings, store)
    orch_b = _orchestrator(session_factory, settings, store)
    for orch in (orch_a, orch_b):
        if hasattr(orch._pipeline._stages[1]._pii, "ensure_ready"):
            await orch._pipeline._stages[1]._pii.ensure_ready()
    out_a = await orch_a.create(
        CreateMemoryCommand(org_id=org_a, agent_id=agent_a, content=content)
    )
    out_b = await orch_b.create(
        CreateMemoryCommand(org_id=org_b, agent_id=agent_b, content=content)
    )
    assert out_a.memory.id != out_b.memory.id
