"""Async SQLAlchemy engine / session helpers (VectorStore in m3.2.1 PR-B)."""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from sqlalchemy import text
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from app.config import Settings


def normalize_async_database_url(url: str) -> str:
    """Map libpq-style DSNs to SQLAlchemy asyncpg URLs.

    asyncpg rejects libpq ``sslmode``; drop it (compose/local use plaintext TLS off).
    """
    raw = url.strip()
    if raw.startswith("postgres://"):
        raw = "postgresql://" + raw[len("postgres://") :]
    if raw.startswith("postgresql://"):
        raw = "postgresql+asyncpg://" + raw[len("postgresql://") :]
    parts = urlsplit(raw)
    query = [
        (k, v) for k, v in parse_qsl(parts.query, keep_blank_values=True) if k != "sslmode"
    ]
    return urlunsplit(
        (parts.scheme, parts.netloc, parts.path, urlencode(query), parts.fragment)
    )


def create_engine(settings: Settings) -> AsyncEngine:
    if not settings.database_url:
        msg = "IBEX_MEMORY_DATABASE_URL is required for database access"
        raise RuntimeError(msg)
    return create_async_engine(
        normalize_async_database_url(settings.database_url),
        pool_pre_ping=True,
    )


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
