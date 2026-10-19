"""Async SQLAlchemy engine / session helpers for worker dead-letter persistence.

The service-account session helpers are the shared implementations from
``ibex_idempotency`` (re-exported here under their historical names) so the
worker and the memory service scope RLS identically for the idempotency ledger.
"""

from __future__ import annotations

from ibex_async_db import parse_async_database_url
from ibex_idempotency.sessions import service_account_session, service_org_session
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from app.config import Settings

# Historical aliases retained for existing worker imports.
session_as_service_account = service_account_session
session_as_service_org = service_org_session

__all__ = [
    "create_engine",
    "create_session_factory",
    "session_as_service_account",
    "session_as_service_org",
]


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
