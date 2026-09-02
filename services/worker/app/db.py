"""Async SQLAlchemy engine / session helpers for worker dead-letter persistence."""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from ibex_async_db import parse_async_database_url
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
        msg = "IBEX_WORKER_DATABASE_URL or POSTGRES_DSN is required for database access"
        raise RuntimeError(msg)
    target = parse_async_database_url(settings.database_url)
    return create_async_engine(
        target.url,
        pool_pre_ping=True,
        connect_args=dict(target.connect_args),
    )


def create_session_factory(engine: AsyncEngine) -> async_sessionmaker[AsyncSession]:
    return async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)


@asynccontextmanager
async def session_as_service_account(
    factory: async_sessionmaker[AsyncSession],
) -> AsyncIterator[AsyncSession]:
    """Open a transaction with service-account GUC (no tenant RLS on failed_tasks)."""
    async with factory() as session:
        try:
            async with session.begin():
                await session.execute(
                    text(  # nosemgrep: python.sqlalchemy.security.audit.avoid-sqlalchemy-text.avoid-sqlalchemy-text
                        "SELECT set_config('app.is_service_account', 'true', true)"
                    )
                )
                yield session
        except Exception:
            await session.rollback()
            raise
