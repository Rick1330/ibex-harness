"""Integration: organizations SELECT under GUC + explicit WHERE (tenant ping SQL)."""

from __future__ import annotations

import os
from uuid import uuid4

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.config import Settings
from app.db import create_session_factory, session_with_org

pytestmark = pytest.mark.integration

_ORG_SELECT = "SELECT id FROM ibex_core.organizations WHERE id = CAST(:org_id AS uuid)"


def _require_dsn() -> str:
    dsn = os.environ.get("IBEX_API_DATABASE_URL") or os.environ.get("IBEX_MEMORY_DATABASE_URL")
    if not dsn:
        pytest.skip("IBEX_API_DATABASE_URL not set")
    return dsn


@pytest.fixture
async def session_factory() -> async_sessionmaker[AsyncSession]:
    settings = Settings(database_url=_require_dsn())
    engine = create_async_engine(settings.database_url, pool_pre_ping=True)  # type: ignore[arg-type]
    factory = create_session_factory(engine)
    try:
        yield factory
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_org_row_visible_with_guc_and_where(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    org_id = uuid4()
    slug = f"api-{org_id.hex[:10]}"

    async with session_factory() as admin, admin.begin():
        await admin.execute(text("SELECT set_config('app.is_service_account', 'true', true)"))
        await admin.execute(
            text(
                "INSERT INTO ibex_core.organizations (id, name, slug) "
                "VALUES (CAST(:id AS uuid), :name, :slug)"
            ),
            {"id": str(org_id), "name": f"Skeleton {slug}", "slug": slug},
        )

    async with session_with_org(session_factory, str(org_id)) as scoped:
        found = (
            await scoped.execute(text(_ORG_SELECT), {"org_id": str(org_id)})
        ).scalar_one_or_none()
        assert found == org_id
