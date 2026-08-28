"""Shared helpers for memory Postgres integration tests (VectorStore + GUC)."""

from __future__ import annotations

import os
from collections.abc import AsyncIterator
from dataclasses import dataclass
from datetime import datetime
from uuid import UUID, uuid4

import pytest
import pytest_asyncio
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from app.config import Settings
from app.db import create_engine, create_session_factory
from app.vectorstore.pgvector_store import PgVectorStore


def _async_dsn_from_env() -> str | None:
    """Pass through DSN; create_engine translates sslmode via connect_args."""
    raw = os.getenv("IBEX_MEMORY_DATABASE_URL") or os.getenv("POSTGRES_TEST_DSN")
    if not raw:
        return None
    if raw.startswith("postgres://"):
        return "postgresql+asyncpg://" + raw[len("postgres://") :]
    if raw.startswith("postgresql://") and "+asyncpg" not in raw.split("://", 1)[0]:
        return "postgresql+asyncpg://" + raw[len("postgresql://") :]
    return raw


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
            await conn.execute(
                text(  # nosemgrep: python.sqlalchemy.security.audit.avoid-sqlalchemy-text.avoid-sqlalchemy-text
                    "SELECT 1"
                )
            )
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


async def _exec_bound(session: AsyncSession, sql: str, params: dict[str, object]) -> None:
    await session.execute(
        text(sql),  # nosemgrep: python.sqlalchemy.security.audit.avoid-sqlalchemy-text.avoid-sqlalchemy-text
        params,
    )


async def with_service_org(session: AsyncSession, org_id: UUID) -> None:
    await _exec_bound(session, "SELECT set_config('app.is_service_account', 'true', true)", {})
    await _exec_bound(
        session,
        "SELECT set_config('app.current_org_id', :org_id, true)",
        {"org_id": str(org_id)},
    )


_ALLOWED_MEMORY_FIELDS = frozenset({"status", "valid_until"})
_MEMORY_FIELD_SQL: dict[str, str] = {
    "status": "SELECT status FROM ibex_core.memories WHERE id = :id AND org_id = :org",
    "valid_until": (
        "SELECT valid_until FROM ibex_core.memories WHERE id = :id AND org_id = :org"
    ),
}


async def fetch_memory_field(
    factory: async_sessionmaker[AsyncSession],
    *,
    org_id: UUID,
    memory_id: UUID,
    field: str,
):
    if field not in _ALLOWED_MEMORY_FIELDS:
        msg = f"unsupported memory field {field!r}"
        raise ValueError(msg)
    async with factory() as session:
        await with_service_org(session, org_id)
        row = (
            await session.execute(
                text(
                    _MEMORY_FIELD_SQL[field]
                ),  # nosemgrep: python.sqlalchemy.security.audit.avoid-sqlalchemy-text.avoid-sqlalchemy-text
                {"id": str(memory_id), "org": str(org_id)},
            )
        ).one()
    return getattr(row, field)


@dataclass(frozen=True, slots=True)
class TimedMemorySeed:
    org_id: UUID
    agent_id: UUID
    memory_id: UUID
    content: str
    content_hash: str
    valid_from: datetime
    valid_until: datetime | None = None
    content_tokens: int = 5


async def insert_timed_memory(
    factory: async_sessionmaker[AsyncSession],
    seed: TimedMemorySeed,
) -> None:
    async with factory() as session, session.begin():
        await with_service_org(session, seed.org_id)
        await _exec_bound(
            session,
            """
            INSERT INTO ibex_core.memories (
                id, org_id, agent_id, content, content_hash, content_tokens,
                valid_from, valid_until
            ) VALUES (
                :id, :org, :agent, :content, :hash, :tokens, :vf, :vu
            )
            """,
            {
                "id": str(seed.memory_id),
                "org": str(seed.org_id),
                "agent": str(seed.agent_id),
                "content": seed.content,
                "hash": seed.content_hash,
                "tokens": seed.content_tokens,
                "vf": seed.valid_from,
                "vu": seed.valid_until,
            },
        )


@dataclass(frozen=True, slots=True)
class _SeedIds:
    org_id: UUID
    user_id: UUID
    agent_id: UUID
    memory_id: UUID
    slug: str
    content: str


async def seed_org_agent_memory(
    factory: async_sessionmaker[AsyncSession],
    *,
    content: str,
) -> tuple[UUID, UUID, UUID]:
    """Insert org/user/agent/memory as service account; return org, agent, memory ids."""
    org_id = uuid4()
    seed = _SeedIds(
        org_id=org_id,
        user_id=uuid4(),
        agent_id=uuid4(),
        memory_id=uuid4(),
        slug=f"org-{org_id.hex[:8]}",
        content=content,
    )
    async with factory() as session, session.begin():
        await _exec_bound(
            session,
            "SELECT set_config('app.is_service_account', 'true', true)",
            {},
        )
        await _insert_seed_rows(session, seed)
    return seed.org_id, seed.agent_id, seed.memory_id


async def _insert_seed_rows(session: AsyncSession, seed: _SeedIds) -> None:
    await _exec_bound(
        session,
        """
        INSERT INTO ibex_core.organizations (id, name, slug)
        VALUES (:id, :name, :slug)
        """,
        {"id": str(seed.org_id), "name": f"Org {seed.slug}", "slug": seed.slug},
    )
    await _exec_bound(
        session,
        """
        INSERT INTO ibex_core.users (id, org_id, email, name)
        VALUES (:id, :org_id, :email, :name)
        """,
        {
            "id": str(seed.user_id),
            "org_id": str(seed.org_id),
            "email": f"{seed.slug}@example.com",
            "name": "User",
        },
    )
    await _exec_bound(
        session,
        """
        INSERT INTO ibex_core.agents (id, org_id, created_by, name, slug)
        VALUES (:id, :org_id, :created_by, :name, :slug)
        """,
        {
            "id": str(seed.agent_id),
            "org_id": str(seed.org_id),
            "created_by": str(seed.user_id),
            "name": "Agent",
            "slug": f"agent-{seed.agent_id.hex[:8]}",
        },
    )
    await _exec_bound(
        session,
        """
        INSERT INTO ibex_core.memories (
            id, org_id, agent_id, content, content_hash, content_tokens
        ) VALUES (
            :id, :org_id, :agent_id, :content, :hash, :tokens
        )
        """,
        {
            "id": str(seed.memory_id),
            "org_id": str(seed.org_id),
            "agent_id": str(seed.agent_id),
            "content": seed.content,
            "hash": f"hash-{seed.memory_id.hex}",
            "tokens": max(1, len(seed.content.split())),
        },
    )


def zero_embedding(dim: int = 1024, *, hotspot: int = 0) -> list[float]:
    vec = [0.0] * dim
    vec[hotspot] = 1.0
    return vec
