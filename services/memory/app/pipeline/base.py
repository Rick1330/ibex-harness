"""Write-pipeline stage protocol (extensible for 3.C.2–3.C.4)."""

from __future__ import annotations

from typing import Protocol

from app.pipeline.context import WriteContext


class Stage(Protocol):
    name: str

    async def process(self, ctx: WriteContext) -> WriteContext:
        """Mutate and return ctx; may set status/flags/content."""
        ...
