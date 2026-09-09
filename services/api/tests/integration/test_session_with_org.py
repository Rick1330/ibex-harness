"""Integration: session_with_org binds app.current_org_id for the management API."""

from __future__ import annotations

import os
from uuid import uuid4

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.db import create_session_factory, session_with_org

pytestmark = pytest.mark.integration


def _require_dsn() -> str:
    dsn = os.environ.get("IBEX_API_DATABASE_URL") or os.environ.get("IBEX_MEMORY_DATABASE_URL")
    if not dsn:
        pytest.skip("IBEX_API_DATABASE_URL not set")
    return dsn


@pytest.fixture
async def session_factory() -> async_sessionmaker[AsyncSession]:
    engine = create_async_engine(_require_dsn(), pool_pre_ping=True)
    factory = create_session_factory(engine)
    try:
        yield factory
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_org_guc_is_transaction_local(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    expected = str(uuid4())
    async with session_with_org(session_factory, expected) as session:
        value = (
            await session.execute(text("SELECT current_setting('app.current_org_id', true)"))
        ).scalar_one()
        assert value == expected

    # Outside the helper, the GUC must not leak across sessions.
    async with session_factory() as session, session.begin():
        leaked = (
            await session.execute(text("SELECT current_setting('app.current_org_id', true)"))
        ).scalar_one()
        assert leaked in (None, "")
