"""Apply memory feedback then refresh hot-cache ZSET (fail-open on Redis)."""

from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.feedback.models import ApplyFeedbackCommand, ApplyFeedbackResult
from app.feedback.persist import apply_feedback_session
from app.write.cache import MemoryCacheWriter


@dataclass(frozen=True, slots=True)
class MemoryFeedbackService:
    session_factory: async_sessionmaker[AsyncSession]
    cache_writer: MemoryCacheWriter | None = None

    async def apply(self, command: ApplyFeedbackCommand) -> ApplyFeedbackResult:
        result, memory = await apply_feedback_session(self.session_factory, command)
        if self.cache_writer is not None:
            await self.cache_writer.refresh_hot(memory)
        return result
