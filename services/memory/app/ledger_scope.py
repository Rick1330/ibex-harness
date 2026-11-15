"""Ledger sessions for the memory service: tenant role, no service bypass.

Two scopes are injected at the ledger's construction site, because the package
defaults are not the identities this service writes as:

* ``tenant_scope`` -- ``claim``/``finalize``/``release`` for one organization.
  Finalization locks the created memory row to serialize with forget, and
  pinning ``ibex_app`` keeps that lock on the tenant's own row.
* ``probe_scope`` -- ``ping()``. The probe asks the catalog whether
  ``current_user`` holds the ledger grants, so the pin has to be inside its
  transaction: the memory login is the ``NOINHERIT`` capability login
  ``ibex_runtime``, which holds no table grant itself. Left unpinned, the probe
  measures the login and reports the ledger as not ready forever.

Neither scope writes ``app.is_service_account``: migration 000063 replaced that
forgeable bypass with ``current_user = 'ibex_service'``, so no policy reads it.
"""

from __future__ import annotations

from collections.abc import AsyncIterator, Callable
from contextlib import AbstractAsyncContextManager, asynccontextmanager
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.org_context import set_service_org, set_service_role


@asynccontextmanager
async def tenant_ledger_session(
    factory: async_sessionmaker[AsyncSession],
    org_id: str,
) -> AsyncIterator[AsyncSession]:
    """Open a ledger transaction as ``ibex_app`` scoped to ``org_id``."""
    async with factory() as session:
        try:
            async with session.begin():
                await set_service_org(session, UUID(org_id))
                yield session
        except Exception:
            await session.rollback()
            raise


def tenant_scope(
    factory: async_sessionmaker[AsyncSession],
) -> Callable[[str], AbstractAsyncContextManager[AsyncSession]]:
    """Return the org-scoped ledger session factory the ledger adapter expects."""

    def _scope(org_id: str) -> AbstractAsyncContextManager[AsyncSession]:
        return tenant_ledger_session(factory, org_id)

    return _scope


@asynccontextmanager
async def probe_ledger_session(
    factory: async_sessionmaker[AsyncSession],
) -> AsyncIterator[AsyncSession]:
    """Open the ledger capability probe as ``ibex_app`` with no tenant claim.

    ``PostgresIdempotencyLedger.ping`` runs
    ``has_table_privilege(current_user, 'ibex_core.idempotency_ledger', ...)``.
    The memory login is ``ibex_runtime``, a ``NOINHERIT`` capability login that
    holds no table grant of its own, so an unpinned probe measures the login and
    reports the ledger as not ready for the life of the process. The probe must
    measure the identity that writes, which is ``ibex_app`` after the pin.

    No organization GUC: the probe reads the catalog, never a ledger row, so a
    tenant predicate would be meaningless. Pinning the role is still required,
    and it is the same pin the write path uses, so a grant the writer does not
    hold cannot be reported as ready.
    """
    async with factory() as session:
        try:
            async with session.begin():
                await set_service_role(session)
                yield session
        except Exception:
            await session.rollback()
            raise


def probe_scope(
    factory: async_sessionmaker[AsyncSession],
) -> Callable[[], AbstractAsyncContextManager[AsyncSession]]:
    """Return the probe scope the ledger adapter expects for ``ping()``."""

    def _scope() -> AbstractAsyncContextManager[AsyncSession]:
        return probe_ledger_session(factory)

    return _scope


__all__ = ["probe_ledger_session", "probe_scope", "tenant_ledger_session", "tenant_scope"]
