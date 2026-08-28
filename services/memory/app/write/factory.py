"""Wire WritePipeline + MemoryWriteOrchestrator from service dependencies."""

from __future__ import annotations

from collections.abc import Awaitable, Callable, Sequence
from uuid import UUID

from app.clients.embedding import EmbeddingClient
from app.conflict.persist import CandidateLoad, load_candidate_memories
from app.conflict.service import ConflictService
from app.dedup.persist import (
    ExactHashLookup,
    RetrievalBump,
    find_active_by_content_hash,
    increment_retrieval_count,
)
from app.dedup.service import DedupService
from app.pipeline import (
    ConflictStage,
    EmbedStage,
    ExactDedupStage,
    NearDedupStage,
    PiiStage,
    ValidateStage,
    WritePipeline,
)
from app.write.embed_context import get_write_org_id
from app.write.models import WriteOutcome
from app.write.orchestrator import MemoryWriteOrchestrator
from app.write.pipeline_deps import WritePipelineDeps


def build_write_pipeline(deps: WritePipelineDeps) -> WritePipeline:
    settings = deps.settings
    session_factory = deps.session_factory

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
    conflict = ConflictService(settings)

    async def load_candidates(org_id: UUID, ids: Sequence[UUID]) -> list:
        return await load_candidate_memories(
            session_factory, CandidateLoad(org_id=org_id, memory_ids=tuple(ids))
        )

    return WritePipeline(
        [
            ValidateStage(settings),
            PiiStage(deps.pii),
            ExactDedupStage(dedup),
            EmbedStage(deps.embed),
            NearDedupStage(dedup),
            ConflictStage(
                conflict,
                load_candidates=load_candidates,
                enabled=settings.conflict_detection_enabled,
            ),
        ]
    )


def build_embedding_callable(
    client: EmbeddingClient,
) -> Callable[[str], Awaitable[list[float]]]:
    async def embed(text: str) -> list[float]:
        result = await client.embed([text], org_id=get_write_org_id())
        return list(result.vectors[0])

    return embed


def build_write_orchestrator(
    deps: WritePipelineDeps,
    *,
    after_commit: Callable[[WriteOutcome], Awaitable[None]] | None = None,
) -> MemoryWriteOrchestrator:
    pipeline = build_write_pipeline(deps)
    return MemoryWriteOrchestrator(
        pipeline,
        deps.session_factory,
        after_commit=after_commit,
    )
