"""Tenant-scoped SQLAlchemy session helpers for the shared idempotency ledger.

The ledger table enforces row-level security, and a transaction is scoped only
when it assumes the role those policies apply to. ``service_org_session``
therefore pins ``ibex_app`` and then sets ``app.current_org_id``, in that order
and transaction-local, mirroring ``packages/pgtenant.PinOrg`` (Go): a GUC set
before the role leaves the statement executing as the login, and under the owner
login the policies do not apply at all, while a ``NOINHERIT`` capability login
(``ibex_runtime``, ``ibex_worker``) holds no table grant of its own and fails
with ``42501``.

Neither helper writes ``app.is_service_account``. Migration 000063 replaced that
forgeable bypass with ``current_user = 'ibex_service'`` in
``ibex_core.rls_org_visible``, so no policy reads the GUC any more.
"""

from __future__ import annotations

from collections.abc import AsyncIterator, Callable
from contextlib import AbstractAsyncContextManager, asynccontextmanager

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

# A callable returning an async context manager yielding an org-scoped session.
SessionScope = Callable[[str], AbstractAsyncContextManager[AsyncSession]]
# A callable returning an async context manager yielding a session with no tenant scope.
ProbeScope = Callable[[], AbstractAsyncContextManager[AsyncSession]]

# The role name is a compile-time constant, never caller input, and PostgreSQL
# cannot bind a role identifier.
_PIN_TENANT_ROLE_SQL = "SET LOCAL ROLE ibex_app"
_SET_ORG_SQL = "SELECT set_config('app.current_org_id', :org_id, true)"


@asynccontextmanager
async def service_account_session(
    factory: async_sessionmaker[AsyncSession],
) -> AsyncIterator[AsyncSession]:
    """Open a transaction with no tenant scope, deliberately unpinned.

    The only caller is ``PostgresIdempotencyLedger.ping()``, which asks the
    catalog (``to_regclass``, ``has_table_privilege``) whether the ledger exists
    and whether the connected identity holds its grants. It reads no row of the
    ledger, so there is no policy to satisfy and nothing to pin: pinning
    ``ibex_app`` here would answer the probe for a different identity than the
    one that writes the ledger, and a probe that reports grants the writer does
    not hold is worse than no probe.

    ``app.is_service_account`` is not set either. No policy has read it since
    migration 000063, so writing it was a forgotten bypass rather than a
    capability.
    """
    async with factory() as session:
        try:
            async with session.begin():
                yield session
        except Exception:
            await session.rollback()
            raise


@asynccontextmanager
async def service_org_session(
    factory: async_sessionmaker[AsyncSession],
    org_id: str,
) -> AsyncIterator[AsyncSession]:
    """Open a transaction as ``ibex_app`` scoped to ``org_id``.

    Role first, then the org GUC, and the order cannot be swapped: the policy
    attached to ``ibex_core.idempotency_ledger`` reads ``app.current_org_id``
    while the effective role is the one that policy applies to, and the
    capability logins hold no table grant of their own.

    ``SET LOCAL`` and ``set_config(..., is_local = true)`` rather than ``SET``
    because the factory behind a store is a pool: session-level state would
    leave ``ibex_app`` and the previous org installed on a connection the next
    request borrows, which is a cross-tenant leak that outlives the request that
    caused it. Both statements are discarded by the commit or rollback that ends
    the transaction.

    A failed pin raises. ``42501`` — the login is not a member of ``ibex_app``,
    or a scoped statement ran without the role — must reach the caller; turning
    it into a silent empty result would make an unscoped transaction look like a
    tenant with no rows.
    """
    async with factory() as session:
        try:
            async with session.begin():
                await session.execute(
                    text(  # nosemgrep: python.sqlalchemy.security.audit.avoid-sqlalchemy-text.avoid-sqlalchemy-text
                        _PIN_TENANT_ROLE_SQL
                    )
                )
                await session.execute(
                    text(  # nosemgrep: python.sqlalchemy.security.audit.avoid-sqlalchemy-text.avoid-sqlalchemy-text
                        _SET_ORG_SQL
                    ),
                    {"org_id": org_id},
                )
                yield session
        except Exception:
            await session.rollback()
            raise


def default_org_scope(
    factory: async_sessionmaker[AsyncSession],
) -> SessionScope:
    """Return the default org-scoped session scope bound to ``factory``."""

    def _scope(org_id: str) -> AbstractAsyncContextManager[AsyncSession]:
        return service_org_session(factory, org_id)

    return _scope


def default_probe_scope(
    factory: async_sessionmaker[AsyncSession],
) -> ProbeScope:
    """Return the default unscoped probe session scope bound to ``factory``."""

    def _scope() -> AbstractAsyncContextManager[AsyncSession]:
        return service_account_session(factory)

    return _scope


__all__ = [
    "ProbeScope",
    "SessionScope",
    "default_org_scope",
    "default_probe_scope",
    "service_account_session",
    "service_org_session",
]
