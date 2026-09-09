"""Integration: organizations SELECT under GUC + explicit WHERE (tenant ping SQL)."""

from __future__ import annotations

import os
from uuid import UUID, uuid4

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.config import Settings
from app.db import create_engine, create_session_factory, session_with_org

pytestmark = pytest.mark.integration

_ORG_SELECT = "SELECT id FROM ibex_core.organizations WHERE id = CAST(:org_id AS uuid)"
_ORG_DELETE = "DELETE FROM ibex_core.organizations WHERE id = CAST(:id AS uuid)"


def _require_dsn() -> str:
    dsn = os.environ.get("IBEX_API_DATABASE_URL") or os.environ.get("IBEX_MEMORY_DATABASE_URL")
    if not dsn:
        pytest.skip("IBEX_API_DATABASE_URL not set")
    return dsn


@pytest.fixture
async def session_factory() -> async_sessionmaker[AsyncSession]:
    settings = Settings(database_url=_require_dsn())
    engine = create_engine(settings)
    factory = create_session_factory(engine)
    try:
        yield factory
    finally:
        await engine.dispose()


async def _insert_org(
    factory: async_sessionmaker[AsyncSession],
    *,
    org_id: UUID,
    slug: str,
) -> None:
    async with factory() as admin, admin.begin():
        await admin.execute(text("SELECT set_config('app.is_service_account', 'true', true)"))
        await admin.execute(
            text(
                "INSERT INTO ibex_core.organizations (id, name, slug) "
                "VALUES (CAST(:id AS uuid), :name, :slug)"
            ),
            {"id": str(org_id), "name": f"Skeleton {slug}", "slug": slug},
        )


async def _delete_orgs(factory: async_sessionmaker[AsyncSession], *org_ids: UUID) -> None:
    async with factory() as admin, admin.begin():
        await admin.execute(text("SELECT set_config('app.is_service_account', 'true', true)"))
        for org_id in org_ids:
            await admin.execute(text(_ORG_DELETE), {"id": str(org_id)})


@pytest.mark.asyncio
async def test_org_row_visible_with_guc_and_where(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    org_a = uuid4()
    org_b = uuid4()
    slug_a = f"api-a-{org_a.hex[:8]}"
    slug_b = f"api-b-{org_b.hex[:8]}"

    try:
        await _insert_org(session_factory, org_id=org_a, slug=slug_a)
        await _insert_org(session_factory, org_id=org_b, slug=slug_b)

        async with session_with_org(session_factory, str(org_a)) as scoped:
            found = (
                await scoped.execute(text(_ORG_SELECT), {"org_id": str(org_a)})
            ).scalar_one_or_none()
            assert found == org_a

        # Cross-tenant: Org B session must not see Org A's row (RLS + WHERE).
        async with session_with_org(session_factory, str(org_b)) as scoped_b:
            leaked = (
                await scoped_b.execute(text(_ORG_SELECT), {"org_id": str(org_a)})
            ).scalar_one_or_none()
            assert leaked is None
    finally:
        await _delete_orgs(session_factory, org_a, org_b)
