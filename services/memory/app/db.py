"""Async SQLAlchemy engine / session helpers (VectorStore in m3.2.1 PR-B)."""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from sqlalchemy import text
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from app.config import Settings


def create_engine(settings: Settings) -> AsyncEngine:
    if not settings.database_url:
        msg = "IBEX_MEMORY_DATABASE_URL is required for database access"
        raise RuntimeError(msg)
    return create_async_engine(settings.database_url, pool_pre_ping=True)


def create_session_factory(engine: AsyncEngine) -> async_sessionmaker[AsyncSession]:
    return async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)


@asynccontextmanager
async def session_with_org(
    factory: async_sessionmaker[AsyncSession],
    org_id: str,
) -> AsyncIterator[AsyncSession]:
    """Open a transaction, set RLS org GUC, yield session, commit/rollback."""
    async with factory() as session:
        try:
            async with session.begin():
                await session.execute(
                    text("SELECT set_config('app.current_org_id', :org_id, true)"),
                    {"org_id": org_id},
                )
                yield session
        except Exception:
            await session.rollback()
            raise
