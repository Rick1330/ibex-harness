"""Concrete write-pipeline stages (validate → pii → exact → embed → near → conflict)."""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable, Sequence
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Protocol
from uuid import UUID

from app.conflict import metrics as conflict_metrics
from app.conflict.intervals import ValidityInterval
from app.conflict.types import (
    CandidateMemory,
    ConflictDecision,
    ConflictOutcome,
    IncomingMemory,
)
from app.dedup import metrics as dedup_metrics
from app.pipeline.context import WriteContext

if TYPE_CHECKING:
    from app.config import Settings
    from app.conflict.service import ConflictService
    from app.dedup.service import DedupService
    from app.pii.service import PiiService


class EmbedCallable(Protocol):
    async def __call__(self, text: str) -> list[float]: ...


CandidateLoader = Callable[[UUID, Sequence[UUID]], Awaitable[list[CandidateMemory]]]


def _validate_content(content: str, max_chars: int) -> str | None:
    """Return an error code, or None when content is acceptable."""
    if not content or not content.strip():
        return "content_empty"
    if len(content) > max_chars:
        return "content_too_long"
    return None


class ValidateStage:
    name = "validate"

    def __init__(self, settings: Settings) -> None:
        self._settings = settings

    async def process(self, ctx: WriteContext) -> WriteContext:
        # Offload sync validation so the Stage Protocol stays async-uniform.
        error = await asyncio.to_thread(
            _validate_content, ctx.content, self._settings.max_content_chars
        )
        if error is not None:
            ctx.stop = True
            ctx.error = error
        return ctx


class PiiStage:
    name = "pii"

    def __init__(self, pii: PiiService) -> None:
        self._pii = pii

    async def process(self, ctx: WriteContext) -> WriteContext:
        result = await self._pii.process_async(ctx.content)
        ctx.findings = list(result.findings)
        ctx.pii_detected = result.pii_detected
        ctx.pii_redacted = result.pii_redacted
        ctx.status = result.status
        ctx.quarantine_reason = result.quarantine_reason
        ctx.content = result.content
        if result.status == "quarantined":
            # Do not embed quarantined content.
            ctx.stop = True
        return ctx


class ExactDedupStage:
    """SHA-256 exact dedup after PII; stops pipeline on hit (skips embed/near-dup)."""

    name = "exact_dedup"

    def __init__(self, dedup: DedupService) -> None:
        self._dedup = dedup

    async def process(self, ctx: WriteContext) -> WriteContext:
        if ctx.agent_id is None:
            ctx.stop = True
            ctx.error = "agent_id_required"
            return ctx
        result = await self._dedup.check_exact(
            org_id=ctx.org_id,
            agent_id=ctx.agent_id,
            content=ctx.content,
        )
        ctx.content_hash = result.content_hash
        if not result.is_exact_duplicate:
            return ctx
        ctx.is_exact_duplicate = True
        ctx.existing_memory_id = result.existing_memory_id
        ctx.stop = True
        dedup_metrics.record_exact_duplicate()
        return ctx


class EmbedStage:
    """Calls the embedder with the current ctx.content (must already be redacted)."""

    name = "embed"

    def __init__(self, embed: EmbedCallable) -> None:
        self._embed = embed

    async def process(self, ctx: WriteContext) -> WriteContext:
        ctx.embedding = await self._embed(ctx.content)
        return ctx


class NearDedupStage:
    """Near-duplicate candidates via VectorStore.search (conflict resolution is 3.C.3)."""

    name = "near_dedup"

    def __init__(self, dedup: DedupService) -> None:
        self._dedup = dedup

    async def process(self, ctx: WriteContext) -> WriteContext:
        if ctx.agent_id is None:
            ctx.stop = True
            ctx.error = "agent_id_required"
            return ctx
        if ctx.embedding is None:
            ctx.stop = True
            ctx.error = "embedding_required"
            return ctx
        candidates = await self._dedup.find_near_duplicates(
            org_id=ctx.org_id,
            agent_id=ctx.agent_id,
            embedding=ctx.embedding,
        )
        ctx.near_duplicate_candidates = candidates
        if candidates:
            dedup_metrics.record_near_duplicate()
        else:
            dedup_metrics.record_novel()
        return ctx


class ConflictStage:
    """Temporal conflict detection after near-dup (ADR-0056)."""

    name = "conflict"

    def __init__(
        self,
        conflict: ConflictService,
        *,
        load_candidates: CandidateLoader,
        enabled: bool = True,
    ) -> None:
        self._conflict = conflict
        self._load = load_candidates
        self._enabled = enabled

    async def process(self, ctx: WriteContext) -> WriteContext:
        if not self._enabled or not ctx.near_duplicate_candidates:
            return ctx
        if ctx.agent_id is None:
            ctx.stop = True
            ctx.error = "agent_id_required"
            return ctx

        candidates = await self._load(ctx.org_id, tuple(ctx.near_duplicate_candidates))
        if not candidates:
            return ctx

        if ctx.valid_from is None:
            evaluation_decisions, llm_calls = await self._escalate_missing_validity(
                ctx, candidates
            )
        else:
            incoming = IncomingMemory(
                content=ctx.content,
                interval=ValidityInterval(
                    valid_from=ctx.valid_from, valid_until=ctx.valid_until
                ),
                memory_id=ctx.existing_memory_id,
            )
            evaluation = await self._conflict.evaluate(incoming, candidates)
            evaluation_decisions = evaluation.decisions
            llm_calls = evaluation.llm_calls

        ctx.conflict_decisions = evaluation_decisions
        ctx.conflict_llm_calls = llm_calls
        ctx.pending_supersede_targets = [
            d.candidate_id
            for d in evaluation_decisions
            if d.outcome == ConflictOutcome.SUPERSEDES
        ]
        _record_conflict_metrics(evaluation_decisions, llm_calls)
        return ctx

    async def _escalate_missing_validity(
        self,
        ctx: WriteContext,
        candidates: list[CandidateMemory],
    ) -> tuple[list[ConflictDecision], int]:
        """ADR-0056: missing valid_from → escalate, never silent skip."""
        placeholder = IncomingMemory(
            content=ctx.content,
            interval=ValidityInterval(valid_from=datetime.now(tz=UTC)),
            memory_id=ctx.existing_memory_id,
        )
        decisions: list[ConflictDecision] = []
        llm_calls = 0
        for candidate in candidates:
            decision = await self._conflict.escalate_pair(
                placeholder, candidate, reason="missing_validity"
            )
            decisions.append(decision)
            if decision.llm_call_made:
                llm_calls += 1
        return decisions, llm_calls


def _record_conflict_metrics(
    decisions: list[ConflictDecision], llm_calls: int
) -> None:
    for decision in decisions:
        conflict_metrics.record_outcome(decision.outcome.value)
    for _ in range(llm_calls):
        conflict_metrics.record_llm_call()
