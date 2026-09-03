"""Persistence tests for PostgresSessionStore GREATEST + org isolation.

Uses the existing migrated_postgres fixture (skips when DSN/migrations absent).
"""

from __future__ import annotations

from uuid import UUID, uuid4

import pytest
import pytest_asyncio
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine, async_sessionmaker

from app.config import Settings
from app.db import create_engine, create_session_factory, session_as_service_account
from app.extraction.session_store import PostgresSessionStore


@pytest_asyncio.fixture
async def pg_engine(migrated_postgres: str) -> AsyncEngine:
    settings = Settings(database_url=migrated_postgres)
    engine = create_engine(settings)
    yield engine
    await engine.dispose()


def _sql(statement: str):
    return text(  # nosemgrep: python.sqlalchemy.security.audit.avoid-sqlalchemy-text.avoid-sqlalchemy-text
        statement
    )


async def _seed_org_agent_session(
    factory: async_sessionmaker,
    *,
    org_id: UUID,
    agent_id: UUID,
    session_id: UUID,
    last_extracted_turn: int,
) -> None:
    slug_org = f"org-{org_id.hex[:8]}"
    slug_agent = f"agent-{agent_id.hex[:8]}"
    async with session_as_service_account(factory) as session:
        await session.execute(
            _sql(
                """
                INSERT INTO ibex_core.organizations (id, name, slug)
                VALUES (:id, :name, :slug)
                """
            ),
            {"id": org_id, "name": f"Org {slug_org}", "slug": slug_org},
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
                "name": "Agent",
                "slug": slug_agent,
            },
        )
        await session.execute(
            _sql(
                """
                INSERT INTO ibex_core.sessions (
                    id, org_id, agent_id, status, model, provider, last_extracted_turn
                ) VALUES (
                    :id, :org_id, :agent_id, 'completed', 'gpt-4o-mini', 'openai', :turn
                )
                """
            ),
            {
                "id": session_id,
                "org_id": org_id,
                "agent_id": agent_id,
                "turn": last_extracted_turn,
            },
        )


async def _read_turn(
    factory: async_sessionmaker, session_id: UUID, org_id: UUID
) -> int:
    async with session_as_service_account(factory) as session:
        row = (
            await session.execute(
                _sql(
                    """
                    SELECT last_extracted_turn
                    FROM ibex_core.sessions
                    WHERE id = :session_id AND org_id = :org_id
                    """
                ),
                {"session_id": session_id, "org_id": org_id},
            )
        ).one()
    return int(row.last_extracted_turn)


@pytest.mark.asyncio
async def test_update_greatest_and_org_isolation(pg_engine: AsyncEngine) -> None:
    factory = create_session_factory(pg_engine)
    org_a, org_b = uuid4(), uuid4()
    agent_a, agent_b = uuid4(), uuid4()
    session_a, session_b = uuid4(), uuid4()
    await _seed_org_agent_session(
        factory, org_id=org_a, agent_id=agent_a, session_id=session_a, last_extracted_turn=5
    )
    await _seed_org_agent_session(
        factory, org_id=org_b, agent_id=agent_b, session_id=session_b, last_extracted_turn=5
    )
    store = PostgresSessionStore(factory)
    await store._update(org_a, session_a, 9)
    await store._update(org_a, session_a, 3)
    await store._update(org_b, session_a, 99)
    assert await _read_turn(factory, session_a, org_a) == 9
    assert await _read_turn(factory, session_b, org_b) == 5
