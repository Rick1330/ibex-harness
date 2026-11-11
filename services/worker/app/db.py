"""Async SQLAlchemy engine / session helpers for worker data access.

Every worker transaction that touches a tenant table runs ``SET LOCAL ROLE``
inside the transaction. The worker login is ``NOINHERIT`` (migration 000064)
and holds no table grants itself, so a tenant read or write needs ``ibex_app``
and the organization-deletion saga needs ``ibex_purge``; neither identity is
available implicitly. ``SET LOCAL`` (never ``SET ROLE``) keeps the identity
inside the transaction, so a pooled connection cannot leak a role into the next
task. The role is pinned *before* the org GUC, in the same order as
``services/memory``, ``services/api`` and ``services/mcp-operator``: one order
across the four services means a copy of this helper cannot diverge. The order
is not load-bearing for RLS -- ``SET ROLE`` preserves transaction-local GUCs and
no role carries an ``app.*`` ``ALTER ROLE ... SET`` -- but a single order is one
less thing to reason about.

The pinned scopes deliberately do not write ``app.is_service_account``. That
GUC stopped being read by any policy in migration 000063; setting it was a
forgotten bypass, not a capability.

Three scopes exist because there are three genuinely different identities:

* ``session_as_app_org`` -- a tenant transaction: ``ibex_app`` plus the row's
  org GUC.
* ``session_as_purge_org`` -- the erasure saga: ``ibex_purge`` plus the org GUC.
* ``session_as_app`` -- ``ibex_app`` with **no** org GUC. Used by capability
  probes (the grant must be checked against the identity the process actually
  writes as) and by the ``failed_tasks`` dead-letter insert (that table has no
  RLS and a nullable ``org_id``; an org GUC there would imply an isolation the
  table does not have).
"""

from __future__ import annotations

from collections.abc import AsyncIterator, Callable
from contextlib import AbstractAsyncContextManager, asynccontextmanager

from ibex_async_db import parse_async_database_url
from sqlalchemy import text
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from app.config import Settings

# Only capability roles the worker is a member of are assignable. The strings
# are constants, never caller input, and PostgreSQL cannot bind a role name.
_PINNED_ROLE_SQL: dict[str, str] = {
    "ibex_app": "SET LOCAL ROLE ibex_app",
    "ibex_purge": "SET LOCAL ROLE ibex_purge",
}
_SET_ORG_SQL = "SELECT set_config('app.current_org_id', :org_id, true)"

__all__ = [
    "app_org_scope",
    "app_probe_scope",
    "create_engine",
    "create_session_factory",
    "session_as_app",
    "session_as_app_org",
    "session_as_purge_org",
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
        # Reached only by a coding error, never by request data. The message
        # names what is allowed and does not echo the rejected value, so a
        # future caller that forwards unvalidated input cannot reflect it here.
        allowed = ", ".join(sorted(_PINNED_ROLE_SQL))
        msg = f"worker capability role must be one of: {allowed}"
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
async def session_as_app(
    factory: async_sessionmaker[AsyncSession],
) -> AsyncIterator[AsyncSession]:
    """Transactional session pinned to ``ibex_app`` with no tenant GUC.

    Two callers, both deliberate:

    * capability probes (``budget_ledger.ping`` and the enqueue
      ``idempotency_ledger.ping``) run ``has_table_privilege(current_user, ...)``.
      The probe must measure the identity the process writes as, so the pin has
      to be inside the transaction; unpinned, ``current_user`` is
      ``ibex_worker``, which holds no table grant, and the probe reports a false
      "not ready".
    * the ``failed_tasks`` dead-letter insert. That table has no RLS (000021),
      ``org_id`` is nullable, and ``ibex_app`` holds INSERT only (000022 revoked
      SELECT), so there is no tenant predicate to bind. An org GUC here would be
      meaningless and would imply an isolation the table does not have.
    """
    async with _transaction(factory) as session:
        await _pin_role(session, "ibex_app")
        yield session


@asynccontextmanager
async def session_as_app_org(
    factory: async_sessionmaker[AsyncSession],
    org_id: str,
) -> AsyncIterator[AsyncSession]:
    """Transactional session pinned to ``ibex_app`` for one tenant."""
    async with _transaction(factory) as session:
        await _pin_role(session, "ibex_app")
        await _bind_org(session, org_id)
        yield session


@asynccontextmanager
async def session_as_purge_org(
    factory: async_sessionmaker[AsyncSession],
    org_id: str,
) -> AsyncIterator[AsyncSession]:
    """Transactional session pinned to ``ibex_purge`` for one tenant."""
    async with _transaction(factory) as session:
        await _pin_role(session, "ibex_purge")
        await _bind_org(session, org_id)
        yield session


def app_org_scope(
    factory: async_sessionmaker[AsyncSession],
) -> Callable[[str], AbstractAsyncContextManager[AsyncSession]]:
    """Bind ``session_as_app_org`` to *factory* for ``PostgresIdempotencyLedger``.

    The shared ledger defaults to a platform scope that only writes the retired
    ``app.is_service_account`` GUC, which under ``ibex_worker`` fails with
    ``42501``. Injecting this scope at the worker's construction site keeps the
    package default unchanged for its other caller (``services/memory``, which
    already injects its own tenant scope).
    """

    def _scope(org_id: str) -> AbstractAsyncContextManager[AsyncSession]:
        return session_as_app_org(factory, org_id)

    return _scope


def app_probe_scope(
    factory: async_sessionmaker[AsyncSession],
) -> Callable[[], AbstractAsyncContextManager[AsyncSession]]:
    """Bind ``session_as_app`` to *factory* for the ledger's ``ping()`` probe."""
    return lambda: session_as_app(factory)
