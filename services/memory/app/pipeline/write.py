"""Ordered write pipeline — validate → pii → exact_dedup → embed → near_dedup."""

from __future__ import annotations

from app.pipeline.base import Stage
from app.pipeline.context import WriteContext


class WritePipeline:
    def __init__(self, stages: list[Stage]) -> None:
        self._stages = list(stages)

    @property
    def stage_names(self) -> list[str]:
        return [s.name for s in self._stages]

    async def run(self, ctx: WriteContext) -> WriteContext:
        for stage in self._stages:
            if ctx.stop:
                break
            ctx = await stage.process(ctx)
        return ctx
