"""Async SQLAlchemy helpers for the management API (RLS org GUC)."""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from ibex_async_db import normalize_async_database_url, parse_async_database_url
from sqlalchemy import text
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from app.config import Settings

# Compose/CI connect as role ``ibex`` (often superuser). Superusers bypass RLS
# even with FORCE ROW LEVEL SECURITY — switch to ``ibex_app`` for enforcement.
_SET_APP_ROLE_SQL = "SET LOCAL ROLE ibex_app"
_CLEAR_SERVICE_ACCOUNT_SQL = "SELECT set_config('app.is_service_account', 'false', true)"
_ORG_GUC_SQL = "SELECT set_config('app.current_org_id', :org_id, true)"


def create_engine(settings: Settings) -> AsyncEngine:
    dsn = settings.database_url
    if not dsn:
        raise RuntimeError("IBEX_API_DATABASE_URL is required for database access")
    parsed = parse_async_database_url(dsn)
    return create_async_engine(
        parsed.url,
        pool_pre_ping=True,
        connect_args=dict(parsed.connect_args),
    )


def create_session_factory(engine: AsyncEngine) -> async_sessionmaker[AsyncSession]:
    return async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)


async def _bind_org_guc(session: AsyncSession, org_id: str) -> None:
    # Bound parameter — not string-interpolated SQL.
    await session.execute(
        text(_SET_APP_ROLE_SQL),  # nosemgrep: python.sqlalchemy.security.audit.avoid-sqlalchemy-text.avoid-sqlalchemy-text
    )
    await session.execute(
        text(_CLEAR_SERVICE_ACCOUNT_SQL),  # nosemgrep: python.sqlalchemy.security.audit.avoid-sqlalchemy-text.avoid-sqlalchemy-text
    )
    await session.execute(
        text(_ORG_GUC_SQL),  # nosemgrep: python.sqlalchemy.security.audit.avoid-sqlalchemy-text.avoid-sqlalchemy-text
        {"org_id": org_id},
    )


@asynccontextmanager
async def session_with_org(
    factory: async_sessionmaker[AsyncSession],
    org_id: str,
) -> AsyncIterator[AsyncSession]:
    """Yield a transactional session with ``app.current_org_id`` bound for RLS."""
    async with factory() as session:
        try:
            async with session.begin():
                await _bind_org_guc(session, org_id)
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
