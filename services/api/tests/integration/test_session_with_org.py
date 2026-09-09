"""Integration: session_with_org GUC against live Postgres."""

from __future__ import annotations

import os
from uuid import uuid4

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.config import Settings
from app.db import create_session_factory, session_with_org

pytestmark = pytest.mark.integration


def _dsn() -> str | None:
    return os.environ.get("IBEX_API_DATABASE_URL") or os.environ.get("IBEX_MEMORY_DATABASE_URL")


@pytest.fixture
async def session_factory() -> async_sessionmaker[AsyncSession]:
    dsn = _dsn()
    if not dsn:
        pytest.skip("IBEX_API_DATABASE_URL not set")
    settings = Settings(database_url=dsn)
    engine = create_async_engine(
        settings.database_url,  # type: ignore[arg-type]
        pool_pre_ping=True,
    )
    factory = create_session_factory(engine)
    yield factory
    await engine.dispose()


@pytest.mark.asyncio
async def test_session_with_org_sets_local_org_guc(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    org_id = str(uuid4())
    async with session_with_org(session_factory, org_id) as session:
        row = await session.execute(
            text("SELECT current_setting('app.current_org_id', true)")
        )
        assert row.scalar_one() == org_id

    async with session_factory() as session, session.begin():
        row = await session.execute(
            text("SELECT current_setting('app.current_org_id', true)")
        )
        assert row.scalar_one() in (None, "")
