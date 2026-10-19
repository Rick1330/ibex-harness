"""Real-PostgreSQL fixtures for the request-idempotency-core.v1 conformance suite.

The suite assumes the database has already been migrated to head (CI applies the
migrations before invoking pytest). It fails closed when no DSN is configured.
"""

from __future__ import annotations

import os
from collections.abc import AsyncIterator
from uuid import UUID, uuid4

import pytest
import pytest_asyncio
from ibex_idempotency import PostgresIdempotencyLedger
from sqlalchemy import text
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

_DSN_ENV = ("IBEX_IDEMPOTENCY_CONFORMANCE_DSN", "POSTGRES_TEST_DSN", "IBEX_MEMORY_DATABASE_URL")


def _async_dsn() -> str | None:
    for name in _DSN_ENV:
        raw = os.getenv(name)
        if not raw:
            continue
        if raw.startswith("postgresql+asyncpg://"):
            return raw
        if raw.startswith("postgres://"):
            return "postgresql+asyncpg://" + raw[len("postgres://") :]
        if raw.startswith("postgresql://"):
            return "postgresql+asyncpg://" + raw[len("postgresql://") :]
        return raw
    return None


@pytest.fixture(scope="session")
def conformance_dsn() -> str:
    dsn = _async_dsn()
    if not dsn:
        pytest.skip("IBEX_IDEMPOTENCY_CONFORMANCE_DSN / POSTGRES_TEST_DSN not set")
    return dsn


@pytest_asyncio.fixture
async def engine(conformance_dsn: str) -> AsyncIterator[AsyncEngine]:
    eng = create_async_engine(conformance_dsn)
    try:
        async with eng.connect() as conn:
            await conn.execute(
                text(  # nosemgrep: python.sqlalchemy.security.audit.avoid-sqlalchemy-text.avoid-sqlalchemy-text
                    "SELECT 1"
                )
            )
    except Exception as exc:  # noqa: BLE001 — environment probe
        await eng.dispose()
        pytest.skip(f"postgres not available: {exc}")
    yield eng
    await eng.dispose()


@pytest.fixture
def session_factory(engine: AsyncEngine) -> async_sessionmaker[AsyncSession]:
    return async_sessionmaker(engine, expire_on_commit=False)


@pytest_asyncio.fixture
async def ledger(
    session_factory: async_sessionmaker[AsyncSession],
) -> AsyncIterator[PostgresIdempotencyLedger]:
    yield PostgresIdempotencyLedger(session_factory, lease_seconds=1.0)


async def _seed_org_agent(session: AsyncSession) -> tuple[UUID, UUID]:
    suffix = uuid4().hex
    org_id = (
        await session.execute(
            text(  # nosemgrep: python.sqlalchemy.security.audit.avoid-sqlalchemy-text.avoid-sqlalchemy-text
                "INSERT INTO ibex_core.organizations (name, slug) "
                "VALUES (:name, :slug) RETURNING id"
            ),
            {"name": "conformance", "slug": f"conformance-{suffix}"},
        )
    ).scalar_one()
    agent_id = (
        await session.execute(
            text(  # nosemgrep: python.sqlalchemy.security.audit.avoid-sqlalchemy-text.avoid-sqlalchemy-text
                "INSERT INTO ibex_core.agents (org_id, name, slug) "
                "VALUES (:org_id, :name, :slug) RETURNING id"
            ),
            {"org_id": org_id, "name": "conformance-agent", "slug": f"conformance-agent-{suffix}"},
        )
    ).scalar_one()
    return org_id, agent_id


@pytest_asyncio.fixture
async def principal(
    session_factory: async_sessionmaker[AsyncSession],
) -> tuple[UUID, UUID]:
    """Seed and return one (org_id, agent_id) under the service-account scope."""
    async with session_factory() as session, session.begin():
        await session.execute(
            text(  # nosemgrep: python.sqlalchemy.security.audit.avoid-sqlalchemy-text.avoid-sqlalchemy-text
                "SELECT set_config('app.is_service_account', 'true', true)"
            )
        )
        org_id, agent_id = await _seed_org_agent(session)
    return org_id, agent_id


@pytest_asyncio.fixture
async def second_principal(
    session_factory: async_sessionmaker[AsyncSession],
) -> tuple[UUID, UUID]:
    async with session_factory() as session, session.begin():
        await session.execute(
            text(  # nosemgrep: python.sqlalchemy.security.audit.avoid-sqlalchemy-text.avoid-sqlalchemy-text
                "SELECT set_config('app.is_service_account', 'true', true)"
            )
        )
        org_id, agent_id = await _seed_org_agent(session)
    return org_id, agent_id
