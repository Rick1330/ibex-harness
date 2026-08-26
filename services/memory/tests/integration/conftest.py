"""Postgres fixtures for memory service integration tests."""

from __future__ import annotations

import os
from collections.abc import AsyncIterator
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

import pytest
import pytest_asyncio
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from app.config import Settings
from app.db import create_engine, create_session_factory


def _async_dsn_from_env() -> str | None:
    raw = os.getenv("IBEX_MEMORY_DATABASE_URL") or os.getenv("POSTGRES_TEST_DSN")
    if not raw:
        return None
    if raw.startswith("postgres://"):
        raw = "postgresql://" + raw[len("postgres://") :]
    if raw.startswith("postgresql://"):
        raw = "postgresql+asyncpg://" + raw[len("postgresql://") :]
    parts = urlsplit(raw)
    query = [
        (k, v) for k, v in parse_qsl(parts.query, keep_blank_values=True) if k != "sslmode"
    ]
    return urlunsplit(
        (parts.scheme, parts.netloc, parts.path, urlencode(query), parts.fragment)
    )


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
