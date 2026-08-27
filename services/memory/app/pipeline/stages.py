"""Concrete write-pipeline stages for m3.C.1 (validate → pii → embed)."""

from __future__ import annotations

from typing import TYPE_CHECKING, Protocol

from app.pipeline.context import WriteContext

if TYPE_CHECKING:
    from app.config import Settings
    from app.pii.service import PiiService


class EmbedCallable(Protocol):
    async def __call__(self, text: str) -> list[float]: ...


class ValidateStage:
    name = "validate"

    def __init__(self, settings: Settings) -> None:
        self._settings = settings

    async def process(self, ctx: WriteContext) -> WriteContext:
        text = ctx.content
        if not text or not text.strip():
            ctx.stop = True
            ctx.error = "content_empty"
            return ctx
        if len(text) > self._settings.max_content_chars:
            ctx.stop = True
            ctx.error = "content_too_long"
            return ctx
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


class EmbedStage:
    """Calls the embedder with the current ctx.content (must already be redacted)."""

    name = "embed"

    def __init__(self, embed: EmbedCallable) -> None:
        self._embed = embed

    async def process(self, ctx: WriteContext) -> WriteContext:
        ctx.embedding = await self._embed(ctx.content)
        return ctx
