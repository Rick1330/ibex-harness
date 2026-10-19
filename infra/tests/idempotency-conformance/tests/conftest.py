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
from ibex_async_db import AsyncDatabaseTarget, parse_async_database_url
from ibex_idempotency import PostgresIdempotencyLedger
from sqlalchemy import text
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

_DSN_ENV = ("IBEX_IDEMPOTENCY_CONFORMANCE_DSN", "POSTGRES_TEST_DSN", "IBEX_MEMORY_DATABASE_URL")


def _raw_dsn() -> str | None:
    for name in _DSN_ENV:
        raw = os.getenv(name)
        if raw:
            return raw
    return None


@pytest.fixture(scope="session")
def conformance_target() -> AsyncDatabaseTarget:
    """Parse the first configured DSN into an asyncpg URL + SSL connect_args.

    ``sslmode`` (as used by the CI libpq DSN) is not a valid asyncpg connect
    kwarg; ``parse_async_database_url`` translates it and strips it so the engine
    can actually connect instead of erroring into a silent skip.
    """
    raw = _raw_dsn()
    if not raw:
        pytest.skip("IBEX_IDEMPOTENCY_CONFORMANCE_DSN / POSTGRES_TEST_DSN not set")
    return parse_async_database_url(raw)


@pytest_asyncio.fixture
async def engine(conformance_target: AsyncDatabaseTarget) -> AsyncIterator[AsyncEngine]:
    eng = create_async_engine(
        conformance_target.url, connect_args=dict(conformance_target.connect_args)
    )
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


async def _scalar_id(session: AsyncSession, statement: str, params: dict[str, object]) -> UUID:
    result = await session.execute(
        text(  # nosemgrep: python.sqlalchemy.security.audit.avoid-sqlalchemy-text.avoid-sqlalchemy-text
            statement
        ),
        params,
    )
    return result.scalar_one()  # type: ignore[no-any-return]


async def _seed_org_agent(session: AsyncSession) -> tuple[UUID, UUID]:
    suffix = uuid4().hex
    org_id = await _scalar_id(
        session,
        "INSERT INTO ibex_core.organizations (name, slug) VALUES (:name, :slug) RETURNING id",
        {"name": "conformance", "slug": f"conformance-{suffix}"},
    )
    agent_id = await _scalar_id(
        session,
        "INSERT INTO ibex_core.agents (org_id, name, slug) "
        "VALUES (:org_id, :name, :slug) RETURNING id",
        {"org_id": org_id, "name": "conformance-agent", "slug": f"conformance-agent-{suffix}"},
    )
    return org_id, agent_id


async def _seed_principal(session_factory: async_sessionmaker[AsyncSession]) -> tuple[UUID, UUID]:
    """Seed and return one (org_id, agent_id) under the service-account scope."""
    async with session_factory() as session, session.begin():
        await session.execute(
            text(  # nosemgrep: python.sqlalchemy.security.audit.avoid-sqlalchemy-text.avoid-sqlalchemy-text
                "SELECT set_config('app.is_service_account', 'true', true)"
            )
        )
        return await _seed_org_agent(session)


@pytest_asyncio.fixture
async def principal(session_factory: async_sessionmaker[AsyncSession]) -> tuple[UUID, UUID]:
    return await _seed_principal(session_factory)


@pytest_asyncio.fixture
async def second_principal(session_factory: async_sessionmaker[AsyncSession]) -> tuple[UUID, UUID]:
    return await _seed_principal(session_factory)
