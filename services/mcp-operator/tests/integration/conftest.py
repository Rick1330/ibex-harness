"""Live-PostgreSQL fixtures for operator read isolation.

The operator connects as ``ibex_app`` with ``app.current_org_id`` bound (RLS);
this module seeds rows as the migration role and tears them down. Skipped when no
database URL is configured (local dev without Docker).
"""

from __future__ import annotations

import os
from collections.abc import AsyncIterator
from dataclasses import dataclass
from uuid import UUID, uuid4

import pytest
from ibex_async_db import normalize_async_database_url
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine, create_async_engine

from app.config import Settings
from app.db import create_engine, create_session_factory
from app.tools import ToolDispatcher

pytestmark = pytest.mark.integration

_ENV_CANDIDATES = (
    "IBEX_MCP_OPERATOR_TEST_DATABASE_URL",
    "IBEX_TEST_DATABASE_URL",
    "IBEX_DATABASE_URL",
    "DATABASE_URL",
)


def _database_url() -> str:
    for name in _ENV_CANDIDATES:
        value = os.environ.get(name, "").strip()
        if value:
            return value
    pytest.skip("no PostgreSQL URL configured for operator integration tests")


@dataclass(frozen=True, slots=True)
class Seeded:
    org_a: UUID
    org_b: UUID
    agent_a: UUID
    agent_b: UUID
    session_a: UUID
    session_b: UUID
    run_a: UUID
    run_b: UUID
    trace_b: str


@pytest.fixture(scope="module")
def database_url() -> str:
    return _database_url()


@pytest.fixture
async def seed_engine(database_url: str) -> AsyncIterator[AsyncEngine]:
    url = normalize_async_database_url(database_url)
    engine = create_async_engine(url, pool_pre_ping=True)
    try:
        yield engine
    finally:
        await engine.dispose()


@pytest.fixture
async def operator_engine(database_url: str) -> AsyncIterator[AsyncEngine]:
    engine = create_engine(Settings(enabled=True, database_url=database_url))
    try:
        yield engine
    finally:
        await engine.dispose()


@pytest.fixture
async def seeded(seed_engine: AsyncEngine) -> AsyncIterator[Seeded]:
    ids = Seeded(
        org_a=uuid4(),
        org_b=uuid4(),
        agent_a=uuid4(),
        agent_b=uuid4(),
        session_a=uuid4(),
        session_b=uuid4(),
        run_a=uuid4(),
        run_b=uuid4(),
        trace_b=uuid4().hex,
    )
    async with seed_engine.begin() as conn:
        await _seed(conn, ids)
    try:
        yield ids
    finally:
        async with seed_engine.begin() as conn:
            await _teardown(conn, ids)


async def _seed(conn: object, ids: Seeded) -> None:
    for org, slug in (
        (ids.org_a, f"op-a-{ids.org_a.hex[:8]}"),
        (ids.org_b, f"op-b-{ids.org_b.hex[:8]}"),
    ):
        await conn.execute(  # type: ignore[attr-defined]
            text("INSERT INTO ibex_core.organizations (id, name, slug) VALUES (:id, :name, :slug)"),
            {"id": str(org), "name": slug, "slug": slug},
        )
    for agent, org, slug in (
        (ids.agent_a, ids.org_a, f"agent-a-{ids.agent_a.hex[:8]}"),
        (ids.agent_b, ids.org_b, f"agent-b-{ids.agent_b.hex[:8]}"),
    ):
        await conn.execute(  # type: ignore[attr-defined]
            text(
                "INSERT INTO ibex_core.agents (id, org_id, name, slug) "
                "VALUES (:id, :org_id, :name, :slug)"
            ),
            {"id": str(agent), "org_id": str(org), "name": slug, "slug": slug},
        )
    for session_id, org, agent in (
        (ids.session_a, ids.org_a, ids.agent_a),
        (ids.session_b, ids.org_b, ids.agent_b),
    ):
        await conn.execute(  # type: ignore[attr-defined]
            text(
                "INSERT INTO ibex_core.sessions (id, org_id, agent_id, status, model, provider) "
                "VALUES (:id, :org_id, :agent_id, 'active', 'gpt-4o-mini', 'openai')"
            ),
            {"id": str(session_id), "org_id": str(org), "agent_id": str(agent)},
        )
    for run_id, org, agent, session_id, request_id, trace_id in (
        (
            ids.run_a,
            ids.org_a,
            ids.agent_a,
            ids.session_a,
            f"req-a-{ids.run_a.hex[:8]}",
            str(uuid4()),
        ),
        (
            ids.run_b,
            ids.org_b,
            ids.agent_b,
            ids.session_b,
            f"req-b-{ids.run_b.hex[:8]}",
            ids.trace_b,
        ),
    ):
        await conn.execute(  # type: ignore[attr-defined]
            text(
                "INSERT INTO ibex_core.evidence_runs "
                "(id, org_id, agent_id, session_id, request_id, trace_id, status, completeness) "
                "VALUES (:id, :org_id, :agent_id, :session_id, :request_id, :trace_id, 'ok', 'complete')"
            ),
            {
                "id": str(run_id),
                "org_id": str(org),
                "agent_id": str(agent),
                "session_id": str(session_id),
                "request_id": request_id,
                "trace_id": trace_id,
            },
        )
    for org, cap in ((ids.org_a, 5000), (ids.org_b, 9000)):
        await conn.execute(  # type: ignore[attr-defined]
            text(
                "INSERT INTO ibex_billing.budget_periods "
                "(org_id, period_start, period_end, cap_cents) "
                "VALUES (:org_id, NOW() - INTERVAL '1 day', NOW() + INTERVAL '1 day', :cap)"
            ),
            {"org_id": str(org), "cap": cap},
        )


async def _teardown(conn: object, ids: Seeded) -> None:
    for org in (ids.org_a, ids.org_b):
        await conn.execute(  # type: ignore[attr-defined]
            text("DELETE FROM ibex_billing.budget_periods WHERE org_id = :org_id"),
            {"org_id": str(org)},
        )
        await conn.execute(  # type: ignore[attr-defined]
            text("DELETE FROM ibex_core.agents WHERE org_id = :org_id"),
            {"org_id": str(org)},
        )
        await conn.execute(  # type: ignore[attr-defined]
            text("DELETE FROM ibex_core.organizations WHERE id = :org_id"),
            {"org_id": str(org)},
        )


@pytest.fixture
def dispatcher(operator_engine: AsyncEngine) -> ToolDispatcher:
    return ToolDispatcher(create_session_factory(operator_engine))
