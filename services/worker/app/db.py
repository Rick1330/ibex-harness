"""Async SQLAlchemy engine / session helpers for worker dead-letter persistence.

Two families of session helpers live here:

* The shared ``ibex_idempotency`` scopes, re-exported under their historical
  names. They are unchanged and are still used by callers that do not need a
  capability role (dead-letter persistence, budget reservations, capture
  redaction).
* The capability-pinned scopes below, which run ``SET LOCAL ROLE`` inside the
  transaction. The worker login is ``NOINHERIT`` (migration 000064), so a
  tenant write needs ``ibex_app`` and the organization-deletion saga needs
  ``ibex_purge``; neither identity is available implicitly. ``SET LOCAL`` (never
  ``SET ROLE``) keeps the identity inside the transaction, so a pooled
  connection cannot leak a role into the next task.

The pinned scopes deliberately do not write ``app.is_service_account``. That
GUC stopped being read by any policy in migration 000063; setting it was a
forgotten bypass, not a capability.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from ibex_async_db import parse_async_database_url
from ibex_idempotency.sessions import service_account_session, service_org_session
from sqlalchemy import text
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

# Only capability roles the worker is a member of are assignable. The strings
# are constants, never caller input, and PostgreSQL cannot bind a role name.
_PINNED_ROLE_SQL: dict[str, str] = {
    "ibex_app": "SET LOCAL ROLE ibex_app",
    "ibex_purge": "SET LOCAL ROLE ibex_purge",
}
_SET_ORG_SQL = "SELECT set_config('app.current_org_id', :org_id, true)"

__all__ = [
    "create_engine",
    "create_session_factory",
    "session_as_app_org",
    "session_as_purge_org",
    "session_as_service_account",
    "session_as_service_org",
    "session_unpinned",
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
        # See services/api/app/db.py: DBAPIError text can carry bound
        # parameters, which include extraction content.
        hide_parameters=True,
    )


def create_session_factory(engine: AsyncEngine) -> async_sessionmaker[AsyncSession]:
    return async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)


@asynccontextmanager
async def _transaction(
    factory: async_sessionmaker[AsyncSession],
) -> AsyncIterator[AsyncSession]:
    async with factory() as session:
        try:
            async with session.begin():
                yield session
        except Exception:
            await session.rollback()
            raise


async def _pin_role(session: AsyncSession, role: str) -> None:
    statement = _PINNED_ROLE_SQL.get(role)
    if statement is None:
        # Reached only by a coding error, never by request data.
        msg = f"role {role!r} is not an assignable worker capability role"
        raise ValueError(msg)
    await session.execute(text(statement))  # nosemgrep: python.sqlalchemy.security.audit.avoid-sqlalchemy-text.avoid-sqlalchemy-text


async def _bind_org(session: AsyncSession, org_id: str) -> None:
    await session.execute(
        text(  # nosemgrep: python.sqlalchemy.security.audit.avoid-sqlalchemy-text.avoid-sqlalchemy-text
            _SET_ORG_SQL
        ),
        {"org_id": org_id},
    )


@asynccontextmanager
async def session_unpinned(
    factory: async_sessionmaker[AsyncSession],
) -> AsyncIterator[AsyncSession]:
    """Transactional session with no role pin.

    Only for ``SECURITY DEFINER`` calls whose cross-tenant reach comes from the
    function owner. Do not run tenant-table DML through this scope.
    """
    async with _transaction(factory) as session:
        yield session


@asynccontextmanager
async def session_as_app_org(
    factory: async_sessionmaker[AsyncSession],
    org_id: str,
) -> AsyncIterator[AsyncSession]:
    """Transactional session pinned to ``ibex_app`` for one tenant."""
    async with _transaction(factory) as session:
        await _bind_org(session, org_id)
        await _pin_role(session, "ibex_app")
        yield session


@asynccontextmanager
async def session_as_purge_org(
    factory: async_sessionmaker[AsyncSession],
    org_id: str,
) -> AsyncIterator[AsyncSession]:
    """Transactional session pinned to ``ibex_purge`` for one tenant."""
    async with _transaction(factory) as session:
        await _bind_org(session, org_id)
        await _pin_role(session, "ibex_purge")
        yield session
