"""Ledger sessions for the memory service: tenant role, no service bypass.

The shared package's default scope is a platform actor (``app.is_service_account``
set and no role pinned). The memory service never needs that reach for its own
ledger: ``claim``/``finalize``/``release`` are all scoped to one organization,
and finalization locks the created memory row to serialize with forget. Pinning
``ibex_app`` keeps that lock on the tenant's own row — a service-account scope
would let it reach any tenant's row, which is exactly the reach this wave
removes.
"""

from __future__ import annotations

from collections.abc import AsyncIterator, Callable
from contextlib import AbstractAsyncContextManager, asynccontextmanager
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.org_context import set_service_org


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


__all__ = ["tenant_ledger_session", "tenant_scope"]
