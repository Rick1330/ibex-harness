"""Tenant-scoped SQLAlchemy session helpers for the shared idempotency ledger.

Every ledger transaction sets its RLS GUCs explicitly (``app.current_org_id``
and, for platform actors, ``app.is_service_account``) even though the ledger
table enforces row-level security. Explicit scoping is defense in depth and
keeps the runtime behavior identical across the proxy (Go), worker, and memory
(Python) ledger callers.
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


@asynccontextmanager
async def service_account_session(
    factory: async_sessionmaker[AsyncSession],
) -> AsyncIterator[AsyncSession]:
    """Open a transaction as the platform actor with no tenant RLS scope."""
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


@asynccontextmanager
async def service_org_session(
    factory: async_sessionmaker[AsyncSession],
    org_id: str,
) -> AsyncIterator[AsyncSession]:
    """Open a transaction as the platform actor scoped to ``org_id``."""
    async with factory() as session:
        try:
            async with session.begin():
                await session.execute(
                    text(  # nosemgrep: python.sqlalchemy.security.audit.avoid-sqlalchemy-text.avoid-sqlalchemy-text
                        "SELECT set_config('app.is_service_account', 'true', true)"
                    )
                )
                await session.execute(
                    text(  # nosemgrep: python.sqlalchemy.security.audit.avoid-sqlalchemy-text.avoid-sqlalchemy-text
                        "SELECT set_config('app.current_org_id', :org_id, true)"
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
