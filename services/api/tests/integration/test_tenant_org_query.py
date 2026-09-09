"""Integration: org-scoped SELECT on ibex_core.organizations (tenant ping query)."""

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
async def test_tenant_org_visible_under_guc_and_where(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    org_id = uuid4()
    slug = f"api-skel-{org_id.hex[:8]}"

    async with session_factory() as session, session.begin():
        await session.execute(
            text("SELECT set_config('app.is_service_account', 'true', true)")
        )
        await session.execute(
            text(
                """
                INSERT INTO ibex_core.organizations (id, name, slug)
                VALUES (CAST(:id AS uuid), :name, :slug)
                """
            ),
            {"id": str(org_id), "name": f"API Skeleton {slug}", "slug": slug},
        )

    async with session_with_org(session_factory, str(org_id)) as session:
        row = await session.execute(
            text(
                "SELECT id FROM ibex_core.organizations WHERE id = CAST(:org_id AS uuid)"
            ),
            {"org_id": str(org_id)},
        )
        assert row.scalar_one_or_none() == org_id
