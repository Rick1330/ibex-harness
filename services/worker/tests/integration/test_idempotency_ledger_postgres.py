"""Real PostgreSQL tests for the worker idempotency ledger.

These tests are skipped unless POSTGRES_DSN, POSTGRES_TEST_DSN, or
IBEX_WORKER_DATABASE_URL points at a migrated dedicated test database.
"""

from __future__ import annotations

from contextlib import asynccontextmanager
from uuid import UUID, uuid4

import pytest
import pytest_asyncio
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine, async_sessionmaker

import app.idempotency_ledger as ledger_module
from app.config import Settings
from app.db import (
    create_engine,
    create_session_factory,
    session_as_service_account,
    session_as_service_org,
)
from app.idempotency_ledger import PostgresIdempotencyLedger

pytestmark = pytest.mark.integration


def _sql(statement: str):
    return text(  # nosemgrep: python.sqlalchemy.security.audit.avoid-sqlalchemy-text.avoid-sqlalchemy-text
        statement
    )


@pytest_asyncio.fixture
async def pg_factory(migrated_postgres: str):
    engine: AsyncEngine = create_engine(Settings(database_url=migrated_postgres))
    factory = create_session_factory(engine)

    @asynccontextmanager
    async def app_org_session(session_factory, org_id: str):
        async with session_factory() as session, session.begin():
            await session.execute(_sql("SET LOCAL ROLE ibex_app"))
            await session.execute(
                _sql("SELECT set_config('app.current_org_id', :org_id, true)"),
                {"org_id": org_id},
            )
            await session.execute(
                _sql("SELECT set_config('app.is_service_account', 'false', true)")
            )
            yield session

    original_session = ledger_module.session_as_service_org
    ledger_module.session_as_service_org = app_org_session
    try:
        yield factory
    finally:
        ledger_module.session_as_service_org = original_session
        await engine.dispose()


async def _seed_org_agent(factory: async_sessionmaker, org_id: UUID, agent_id: UUID) -> None:
    async with session_as_service_account(factory) as session:
        await session.execute(
            _sql(
                """
                INSERT INTO ibex_core.organizations (id, name, slug)
                VALUES (:id, :name, :slug)
                """
            ),
            {"id": org_id, "name": f"Ledger {org_id.hex[:8]}", "slug": f"ledger-{org_id.hex[:12]}"},
        )
        await session.execute(
            _sql(
                """
                INSERT INTO ibex_core.agents (id, org_id, name, slug)
                VALUES (:id, :org_id, :name, :slug)
                """
            ),
            {
                "id": agent_id,
                "org_id": org_id,
                "name": "Ledger test agent",
                "slug": f"ledger-agent-{agent_id.hex[:12]}",
            },
        )


async def _delete_seed(factory: async_sessionmaker, org_id: UUID, agent_id: UUID) -> None:
    async with session_as_service_account(factory) as session:
        await session.execute(
            _sql("DELETE FROM ibex_core.agents WHERE id = :id AND org_id = :org_id"),
            {"id": agent_id, "org_id": org_id},
        )
        await session.execute(
            _sql("DELETE FROM ibex_core.organizations WHERE id = :id"), {"id": org_id}
        )


@pytest.mark.asyncio
async def test_ledger_real_postgres_isolates_organizations_and_allows_release(pg_factory) -> None:
    org_a, org_b = uuid4(), uuid4()
    agent_a, agent_b = uuid4(), uuid4()
    await _seed_org_agent(pg_factory, org_a, agent_a)
    await _seed_org_agent(pg_factory, org_b, agent_b)
    try:
        ledger = PostgresIdempotencyLedger(pg_factory, lease_seconds=30)
        hash_a = "a" * 64
        hash_b = "b" * 64

        claim_a = await ledger.claim(
            org_id=org_a, agent_id=agent_a, key="same-key", request_hash=hash_a
        )
        assert claim_a.kind == "owned"
        assert claim_a.claim is not None
        await ledger.finalize(claim_a.claim, status=202, response=b'{"task_id":"a"}')

        replay_a = await ledger.claim(
            org_id=org_a, agent_id=agent_a, key="same-key", request_hash=hash_a
        )
        assert replay_a.kind == "replay"
        assert replay_a.response == b'{"task_id":"a"}'

        claim_b = await ledger.claim(
            org_id=org_b, agent_id=agent_b, key="same-key", request_hash=hash_b
        )
        assert claim_b.kind == "owned"
        assert claim_b.claim is not None
        await ledger.release(claim_b.claim)

        async with session_as_service_org(pg_factory, str(org_a)) as session:
            visible_a = (
                await session.execute(
                    _sql(
                        "SELECT count(*) FROM ibex_core.idempotency_ledger "
                        "WHERE organization_id IN (:org_a, :org_b)"
                    ),
                    {"org_a": org_a, "org_b": org_b},
                )
            ).scalar_one()
        async with session_as_service_org(pg_factory, str(org_b)) as session:
            visible_b = (
                await session.execute(
                    _sql(
                        "SELECT count(*) FROM ibex_core.idempotency_ledger "
                        "WHERE organization_id IN (:org_a, :org_b)"
                    ),
                    {"org_a": org_a, "org_b": org_b},
                )
            ).scalar_one()

        assert visible_a == 1
        assert visible_b == 0
    finally:
        await _delete_seed(pg_factory, org_a, agent_a)
        await _delete_seed(pg_factory, org_b, agent_b)
