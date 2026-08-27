"""Concrete write-pipeline stages (validate → pii → exact_dedup → embed → near_dedup)."""

from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING, Protocol

from app.dedup import metrics as dedup_metrics
from app.pipeline.context import WriteContext

if TYPE_CHECKING:
    from app.config import Settings
    from app.dedup.service import DedupService
    from app.pii.service import PiiService


class EmbedCallable(Protocol):
    async def __call__(self, text: str) -> list[float]: ...


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
