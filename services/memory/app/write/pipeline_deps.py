"""Dependencies for assembling the memory write pipeline."""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import dataclass

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.config import Settings
from app.pii.service import PiiService
from app.vectorstore.base import VectorStore


@dataclass(frozen=True, slots=True)
class WritePipelineDeps:
    settings: Settings
    session_factory: async_sessionmaker[AsyncSession]
    store: VectorStore
    pii: PiiService
    embed: Callable[[str], Awaitable[list[float]]]
