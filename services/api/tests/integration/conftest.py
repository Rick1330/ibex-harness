"""Shared fixtures for API integration tests that need live PostgreSQL."""

from __future__ import annotations

import os
from collections.abc import AsyncIterator

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.config import Settings
from app.db import create_engine, create_session_factory

CURSOR_SECRET = "cursor-secret-32-bytes-minimum!!"


def require_dsn() -> str:
    dsn = os.environ.get("IBEX_API_DATABASE_URL") or os.environ.get("POSTGRES_TEST_DSN")
    if not dsn:
        pytest.skip("IBEX_API_DATABASE_URL or POSTGRES_TEST_DSN not set")
    return dsn


@pytest.fixture
async def session_factory() -> AsyncIterator[async_sessionmaker[AsyncSession]]:
    engine = create_engine(
        Settings(database_url=require_dsn(), operator_cursor_secret=CURSOR_SECRET)
    )
    factory = create_session_factory(engine)
    try:
        yield factory
    finally:
        await engine.dispose()
