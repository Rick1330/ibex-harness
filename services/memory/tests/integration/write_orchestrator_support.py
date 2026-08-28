"""Shared helpers for MemoryWriteOrchestrator integration tests."""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from datetime import datetime
from uuid import UUID, uuid4

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.config import Settings
from app.conflict.service import ConflictService
from app.dedup.hash import content_hash_sha256
from app.dedup.persist import (
    ExactHashLookup,
    RetrievalBump,
    find_active_by_content_hash,
    increment_retrieval_count,
)
from app.dedup.service import DedupService
from app.pii.service import PiiService
from app.pii.types import PiiFinding, PiiProcessResult
from app.pipeline import (
    ConflictStage,
    EmbedStage,
    ExactDedupStage,
    NearDedupStage,
    PiiStage,
    ValidateStage,
    WritePipeline,
)
from app.vectorstore.base import UpsertRequest
from app.write.orchestrator import MemoryWriteOrchestrator
from tests.integration.conftest import TimedMemorySeed, insert_timed_memory, zero_embedding


class EmbedProbe:
    def __init__(self) -> None:
        self.seen: list[str] = []

    async def __call__(self, payload: str) -> list[float]:
        self.seen.append(payload)
        return zero_embedding(hotspot=3)


class QuarantinePii:
    async def process_async(self, content: str) -> PiiProcessResult:
        return PiiProcessResult(
            findings=[PiiFinding("PERSON", 0, min(6, len(content)), 0.40)],
            content=content,
            pii_detected=True,
            pii_redacted=False,
            status="quarantined",
            quarantine_reason="pii_low_confidence",
        )


@dataclass(frozen=True, slots=True)
class OrchestratorTestDeps:
    session_factory: async_sessionmaker[AsyncSession]
    settings: Settings
    store: object
    embed: Callable[[str], Awaitable[list[float]]] | None = None
    pii: PiiService | QuarantinePii | None = None
    subject_extractor: Callable[[str], str] | None = None


@dataclass(frozen=True, slots=True)
class VectorMemorySeed:
    org_id: UUID
    agent_id: UUID
    content: str
    valid_from: datetime
    valid_until: datetime | None = None
    hotspot: int = 5


async def ensure_pii_ready(orch: MemoryWriteOrchestrator) -> None:
    pii = orch._pipeline._stages[1]._pii
    if hasattr(pii, "ensure_ready"):
        await pii.ensure_ready()


def build_orchestrator(deps: OrchestratorTestDeps) -> MemoryWriteOrchestrator:
    from app.conflict.persist import CandidateLoad, load_candidate_memories

    session_factory = deps.session_factory
    settings = deps.settings
    probe = deps.embed or EmbedProbe()
    pii_svc = deps.pii or PiiService(settings)
    extract = deps.subject_extractor or (lambda _: "shared-subject-key")

    async def lookup(org_id: UUID, agent_id: UUID, content_hash: str) -> UUID | None:
        return await find_active_by_content_hash(
            session_factory,
            ExactHashLookup(org_id=org_id, agent_id=agent_id, content_hash=content_hash),
        )

    async def bump(org_id: UUID, memory_id: UUID) -> int:
        return await increment_retrieval_count(
            session_factory, RetrievalBump(org_id=org_id, memory_id=memory_id)
        )

    dedup = DedupService(
        settings, store=deps.store, exact_lookup=lookup, bump_retrieval=bump
    )
    conflict = ConflictService(settings, subject_extractor=extract)

    async def load_candidates(org_id: UUID, ids: tuple[UUID, ...]):
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
            ConflictStage(conflict, load_candidates=load_candidates, enabled=True),
        ]
    )
    return MemoryWriteOrchestrator(pipeline, session_factory)


async def set_content_hash(
    factory: async_sessionmaker[AsyncSession],
    *,
    org_id: UUID,
    memory_id: UUID,
    content_hash: str,
) -> None:
    from sqlalchemy import text

    from tests.integration.conftest import with_service_org

    async with factory() as session, session.begin():
        await with_service_org(session, org_id)
        await session.execute(
            text(
                """
                UPDATE ibex_core.memories
                SET content_hash = :hash
                WHERE id = :id AND org_id = :org_id
                """
            ),  # nosemgrep: python.sqlalchemy.security.audit.avoid-sqlalchemy-text.avoid-sqlalchemy-text
            {"hash": content_hash, "id": str(memory_id), "org_id": str(org_id)},
        )


async def seed_vector_memory(
    session_factory: async_sessionmaker[AsyncSession],
    store,
    seed: VectorMemorySeed,
) -> tuple[UUID, list[float]]:
    memory_id = uuid4()
    vec = zero_embedding(hotspot=seed.hotspot)
    await insert_timed_memory(
        session_factory,
        TimedMemorySeed(
            org_id=seed.org_id,
            agent_id=seed.agent_id,
            memory_id=memory_id,
            content=seed.content,
            content_hash=content_hash_sha256(seed.content),
            valid_from=seed.valid_from,
            valid_until=seed.valid_until,
        ),
    )
    await store.upsert(
        UpsertRequest(
            memory_id=memory_id,
            org_id=seed.org_id,
            embedding=vec,
            embedding_model="test-model",
        )
    )
    return memory_id, vec
