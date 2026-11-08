"""Async SQLAlchemy engine / session helpers (VectorStore in m3.2.1 PR-B)."""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from uuid import UUID

from ibex_async_db import normalize_async_database_url, parse_async_database_url
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from app.config import Settings
from app.org_context import set_service_org


def create_engine(settings: Settings) -> AsyncEngine:
    if not settings.database_url:
        msg = "IBEX_MEMORY_DATABASE_URL is required for database access"
        raise RuntimeError(msg)
    target = parse_async_database_url(settings.database_url)
    return create_async_engine(
        target.url,
        pool_pre_ping=True,
        connect_args=dict(target.connect_args),
        # Defence in depth: a statement error must never render bound parameters
        # (``query_text`` on the full-text path) into a log line or span event.
        hide_parameters=True,
    )


def create_session_factory(engine: AsyncEngine) -> async_sessionmaker[AsyncSession]:
    return async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)


@asynccontextmanager
async def session_with_org(
    factory: async_sessionmaker[AsyncSession],
    org_id: str,
) -> AsyncIterator[AsyncSession]:
    """Open a transaction, pin the tenant role and org, yield, commit/rollback.

    Delegates to :func:`app.org_context.set_service_org`, so this helper and the
    production path share one definition: pin ``ibex_app`` (the login role is a
    superuser, and a superuser bypasses RLS before the policy is consulted —
    ``FORCE ROW LEVEL SECURITY`` covers owners, not superusers) and clear any
    inherited service-account bypass.
    """
    async with factory() as session:
        try:
            async with session.begin():
                await set_service_org(session, UUID(org_id))
                yield session
        except Exception:
            await session.rollback()
            raise


__all__ = [
    "create_engine",
    "create_session_factory",
    "normalize_async_database_url",
    "parse_async_database_url",
    "session_with_org",
]
