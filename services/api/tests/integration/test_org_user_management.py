"""Integration: org/user management anti-enumeration and last-owner (live Postgres)."""

from __future__ import annotations

import os
from uuid import uuid4

import pytest
from authclient.permissions import ADMIN
from authclient.revoke import NoopTokenRevoker
from fastapi.testclient import TestClient
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.auth.client import StaticTokenValidator, ValidateResult
from app.config import Settings
from app.db import create_engine, create_session_factory
from app.main import ApiRuntimeOverrides, create_app
from app.revocation_publish import RecordingOrgSuspendPublisher

pytestmark = pytest.mark.integration


def _require_dsn() -> str:
    dsn = os.environ.get("IBEX_API_DATABASE_URL") or os.environ.get("IBEX_MEMORY_DATABASE_URL")
    if not dsn:
        pytest.skip("IBEX_API_DATABASE_URL not set")
    return dsn


async def _sa(factory: async_sessionmaker[AsyncSession], sql: str, params: dict) -> None:
    async with factory() as session, session.begin():
        await session.execute(text("SELECT set_config('app.is_service_account', 'true', true)"))
        await session.execute(text(sql), params)


@pytest.fixture
async def factory() -> async_sessionmaker[AsyncSession]:
    settings = Settings(database_url=_require_dsn())
    engine = create_engine(settings)
    fac = create_session_factory(engine)
    try:
        yield fac
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_cross_tenant_org_get_is_404(factory: async_sessionmaker[AsyncSession]) -> None:
    org_a = uuid4()
    org_b = uuid4()
    user_a = uuid4()
    slug_a = f"cta-{org_a.hex[:8]}"
    slug_b = f"ctb-{org_b.hex[:8]}"
    try:
        await _sa(
            factory,
            "INSERT INTO ibex_core.organizations (id, name, slug) VALUES "
            "(CAST(:id AS uuid), :name, :slug)",
            {"id": str(org_a), "name": "A", "slug": slug_a},
        )
        await _sa(
            factory,
            "INSERT INTO ibex_core.organizations (id, name, slug) VALUES "
            "(CAST(:id AS uuid), :name, :slug)",
            {"id": str(org_b), "name": "B", "slug": slug_b},
        )
        await _sa(
            factory,
            "INSERT INTO ibex_core.users (id, org_id, email, name, role, status) VALUES "
            "(CAST(:id AS uuid), CAST(:org AS uuid), :email, :name, 'owner', 'active')",
            {
                "id": str(user_a),
                "org": str(org_a),
                "email": f"owner-{org_a.hex[:8]}@example.com",
                "name": "Owner A",
            },
        )

        settings = Settings(database_url=_require_dsn())
        validator = StaticTokenValidator(
            {
                "tok-a": ValidateResult(
                    org_id=org_a, permissions=ADMIN, user_id=str(user_a)
                )
            }
        )
        app = create_app(
            settings=settings,
            validator=validator,
            runtime=ApiRuntimeOverrides(
                token_revoker=NoopTokenRevoker(),
                org_suspend_publisher=RecordingOrgSuspendPublisher(),
            ),
        )
        with TestClient(app) as client:
            # Same-org GET works
            ok = client.get(
                f"/v1/organizations/{org_a}",
                headers={"Authorization": "Bearer tok-a"},
            )
            assert ok.status_code == 200
            # Cross-tenant path → 404 (not 403)
            leaked = client.get(
                f"/v1/organizations/{org_b}",
                headers={"Authorization": "Bearer tok-a"},
            )
            assert leaked.status_code == 404
            assert leaked.json()["error"]["code"] == "NOT_FOUND"
    finally:
        await _sa(factory, "DELETE FROM ibex_core.users WHERE org_id = CAST(:id AS uuid)", {"id": str(org_a)})
        await _sa(factory, "DELETE FROM ibex_core.organizations WHERE id = CAST(:id AS uuid)", {"id": str(org_a)})
        await _sa(factory, "DELETE FROM ibex_core.organizations WHERE id = CAST(:id AS uuid)", {"id": str(org_b)})


@pytest.mark.asyncio
async def test_last_owner_demotion_409(factory: async_sessionmaker[AsyncSession]) -> None:
    org_id = uuid4()
    owner_id = uuid4()
    slug = f"lo-{org_id.hex[:8]}"
    try:
        await _sa(
            factory,
            "INSERT INTO ibex_core.organizations (id, name, slug) VALUES "
            "(CAST(:id AS uuid), :name, :slug)",
            {"id": str(org_id), "name": "LastOwner", "slug": slug},
        )
        await _sa(
            factory,
            "INSERT INTO ibex_core.users (id, org_id, email, name, role, status) VALUES "
            "(CAST(:id AS uuid), CAST(:org AS uuid), :email, :name, 'owner', 'active')",
            {
                "id": str(owner_id),
                "org": str(org_id),
                "email": f"solo-{org_id.hex[:8]}@example.com",
                "name": "Solo Owner",
            },
        )
        settings = Settings(database_url=_require_dsn())
        validator = StaticTokenValidator(
            {
                "tok": ValidateResult(
                    org_id=org_id, permissions=ADMIN, user_id=str(owner_id)
                )
            }
        )
        app = create_app(
            settings=settings,
            validator=validator,
            runtime=ApiRuntimeOverrides(
                token_revoker=NoopTokenRevoker(),
                org_suspend_publisher=RecordingOrgSuspendPublisher(),
            ),
        )
        with TestClient(app) as client:
            resp = client.patch(
                f"/v1/users/{owner_id}",
                headers={"Authorization": "Bearer tok"},
                json={"role": "admin"},
            )
            assert resp.status_code == 409
            assert resp.json()["error"]["code"] == "LAST_OWNER_PROTECTED"
    finally:
        await _sa(factory, "DELETE FROM ibex_core.users WHERE org_id = CAST(:id AS uuid)", {"id": str(org_id)})
        await _sa(factory, "DELETE FROM ibex_core.organizations WHERE id = CAST(:id AS uuid)", {"id": str(org_id)})


@pytest.mark.asyncio
async def test_suspend_persists_and_publishes(
    factory: async_sessionmaker[AsyncSession],
) -> None:
    org_id = uuid4()
    owner_id = uuid4()
    slug = f"sus-{org_id.hex[:8]}"
    pub = RecordingOrgSuspendPublisher()
    try:
        await _sa(
            factory,
            "INSERT INTO ibex_core.organizations (id, name, slug) VALUES "
            "(CAST(:id AS uuid), :name, :slug)",
            {"id": str(org_id), "name": "SuspendMe", "slug": slug},
        )
        await _sa(
            factory,
            "INSERT INTO ibex_core.users (id, org_id, email, name, role, status) VALUES "
            "(CAST(:id AS uuid), CAST(:org AS uuid), :email, :name, 'owner', 'active')",
            {
                "id": str(owner_id),
                "org": str(org_id),
                "email": f"sus-{org_id.hex[:8]}@example.com",
                "name": "Owner",
            },
        )
        settings = Settings(database_url=_require_dsn())
        app = create_app(
            settings=settings,
            validator=StaticTokenValidator(
                {
                    "tok": ValidateResult(
                        org_id=org_id, permissions=ADMIN, user_id=str(owner_id)
                    )
                }
            ),
            runtime=ApiRuntimeOverrides(
                token_revoker=NoopTokenRevoker(),
                org_suspend_publisher=pub,
            ),
        )
        with TestClient(app) as client:
            resp = client.post(
                f"/v1/organizations/{org_id}/suspend",
                headers={"Authorization": "Bearer tok"},
            )
            assert resp.status_code == 200
            assert resp.json()["status"] == "suspended"
            assert pub.org_ids == [str(org_id)]
            assert pub.payloads[0]["event_type"] == "org_suspend"
    finally:
        await _sa(factory, "DELETE FROM ibex_core.users WHERE org_id = CAST(:id AS uuid)", {"id": str(org_id)})
        await _sa(factory, "DELETE FROM ibex_core.organizations WHERE id = CAST(:id AS uuid)", {"id": str(org_id)})
