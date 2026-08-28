"""Shared helpers for MemoryWriteOrchestrator integration tests."""

from __future__ import annotations

from collections.abc import Awaitable, Callable
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
from tests.integration.conftest import (
    insert_timed_memory,
    zero_embedding,
)


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


async def ensure_pii_ready(orch: MemoryWriteOrchestrator) -> None:
    pii = orch._pipeline._stages[1]._pii
    if hasattr(pii, "ensure_ready"):
        await pii.ensure_ready()


def build_orchestrator(
    session_factory: async_sessionmaker[AsyncSession],
    settings: Settings,
    store,
    *,
    embed: Callable[[str], Awaitable[list[float]]] | None = None,
    pii: PiiService | QuarantinePii | None = None,
    subject_extractor: Callable[[str], str] | None = None,
) -> MemoryWriteOrchestrator:
    from app.conflict.persist import CandidateLoad, load_candidate_memories

    probe = embed or EmbedProbe()
    pii_svc = pii or PiiService(settings)
    extract = subject_extractor or (lambda _: "shared-subject-key")

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
        settings, store=store, exact_lookup=lookup, bump_retrieval=bump
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
            ),
            {"hash": content_hash, "id": str(memory_id), "org_id": str(org_id)},
        )


async def seed_vector_memory(
    session_factory: async_sessionmaker[AsyncSession],
    store,
    *,
    org_id: UUID,
    agent_id: UUID,
    content: str,
    valid_from: datetime,
    valid_until: datetime | None = None,
    hotspot: int = 5,
) -> tuple[UUID, list[float]]:
    memory_id = uuid4()
    vec = zero_embedding(hotspot=hotspot)
    await insert_timed_memory(
        session_factory,
        org_id=org_id,
        agent_id=agent_id,
        memory_id=memory_id,
        content=content,
        content_hash=content_hash_sha256(content),
        valid_from=valid_from,
        valid_until=valid_until,
    )
    await store.upsert(
        UpsertRequest(
            memory_id=memory_id,
            org_id=org_id,
            embedding=vec,
            embedding_model="test-model",
        )
    )
    return memory_id, vec
