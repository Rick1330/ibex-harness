"""Shared helpers for memory Postgres integration tests (VectorStore + GUC)."""

from __future__ import annotations

import os
from collections.abc import AsyncIterator
from uuid import UUID, uuid4

import pytest
import pytest_asyncio
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from app.config import Settings
from app.db import create_engine, create_session_factory, normalize_async_database_url
from app.vectorstore.pgvector_store import PgVectorStore


def _async_dsn_from_env() -> str | None:
    raw = os.getenv("IBEX_MEMORY_DATABASE_URL") or os.getenv("POSTGRES_TEST_DSN")
    if not raw:
        return None
    return normalize_async_database_url(raw)


@pytest.fixture(scope="module")
def memory_database_url() -> str:
    dsn = _async_dsn_from_env()
    if not dsn:
        pytest.skip("IBEX_MEMORY_DATABASE_URL / POSTGRES_TEST_DSN not set")
    return dsn


@pytest_asyncio.fixture
async def engine(memory_database_url: str) -> AsyncIterator[AsyncEngine]:
    settings = Settings(database_url=memory_database_url)
    eng = create_engine(settings)
    try:
        async with eng.connect() as conn:
            await conn.execute(text("SELECT 1"))
            await conn.commit()
    except Exception as exc:  # noqa: BLE001 — skip if DB unreachable
        await eng.dispose()
        pytest.skip(f"postgres not available: {exc}")
    yield eng
    await eng.dispose()


@pytest.fixture
def session_factory(engine: AsyncEngine) -> async_sessionmaker[AsyncSession]:
    return create_session_factory(engine)


@pytest.fixture
def settings(memory_database_url: str) -> Settings:
    return Settings(database_url=memory_database_url)


@pytest.fixture
def store(
    session_factory: async_sessionmaker[AsyncSession], settings: Settings
) -> PgVectorStore:
    return PgVectorStore(session_factory, settings)


async def seed_org_agent_memory(
    factory: async_sessionmaker[AsyncSession],
    *,
    content: str,
) -> tuple[UUID, UUID, UUID]:
    """Insert org/user/agent/memory as service account; return org, agent, memory ids."""
    org_id = uuid4()
    user_id = uuid4()
    agent_id = uuid4()
    memory_id = uuid4()
    slug = f"org-{org_id.hex[:8]}"
    async with factory() as session, session.begin():
        await session.execute(
            text("SELECT set_config('app.is_service_account', 'true', true)")
        )
        await session.execute(
            text(
                """
                INSERT INTO ibex_core.organizations (id, name, slug)
                VALUES (:id, :name, :slug)
                """
            ),
            {"id": str(org_id), "name": f"Org {slug}", "slug": slug},
        )
        await session.execute(
            text(
                """
                INSERT INTO ibex_core.users (id, org_id, email, name)
                VALUES (:id, :org_id, :email, :name)
                """
            ),
            {
                "id": str(user_id),
                "org_id": str(org_id),
                "email": f"{slug}@example.com",
                "name": "User",
            },
        )
        await session.execute(
            text(
                """
                INSERT INTO ibex_core.agents (id, org_id, created_by, name, slug)
                VALUES (:id, :org_id, :created_by, :name, :slug)
                """
            ),
            {
                "id": str(agent_id),
                "org_id": str(org_id),
                "created_by": str(user_id),
                "name": "Agent",
                "slug": f"agent-{agent_id.hex[:8]}",
            },
        )
        await session.execute(
            text(
                """
                INSERT INTO ibex_core.memories (
                    id, org_id, agent_id, content, content_hash, content_tokens
                ) VALUES (
                    :id, :org_id, :agent_id, :content, :hash, :tokens
                )
                """
            ),
            {
                "id": str(memory_id),
                "org_id": str(org_id),
                "agent_id": str(agent_id),
                "content": content,
                "hash": f"hash-{memory_id.hex}",
                "tokens": max(1, len(content.split())),
            },
        )
    return org_id, agent_id, memory_id


def zero_embedding(dim: int = 1024, *, hotspot: int = 0) -> list[float]:
    vec = [0.0] * dim
    vec[hotspot] = 1.0
    return vec
