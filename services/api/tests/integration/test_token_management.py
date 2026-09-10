"""Integration: token management ISO 404 (FakeTokenManager + live Postgres session)."""

from __future__ import annotations

import os
from collections.abc import AsyncIterator
from datetime import UTC, datetime
from uuid import UUID, uuid4

import pytest
from authclient.permissions import ADMIN, MEMORY_READ
from authclient.revoke import NoopTokenRevoker
from authclient.tokens import FakeTokenManager, TokenMetadataWire
from fastapi.testclient import TestClient
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.auth.client import StaticTokenValidator, ValidateResult
from app.config import Settings
from app.db import create_engine, create_session_factory
from app.main import ApiRuntimeOverrides, create_app
from app.revocation_publish import RecordingOrgSuspendPublisher

pytestmark = pytest.mark.integration
_AUTH = {"Authorization": "Bearer tok"}


def _require_dsn() -> str:
    dsn = os.environ.get("IBEX_API_DATABASE_URL") or os.environ.get("IBEX_MEMORY_DATABASE_URL")
    if not dsn:
        pytest.skip("IBEX_API_DATABASE_URL not set")
    return dsn


@pytest.fixture
async def factory() -> AsyncIterator[async_sessionmaker[AsyncSession]]:
    settings = Settings(database_url=_require_dsn())
    engine = create_engine(settings)
    fac = create_session_factory(engine)
    try:
        yield fac
    finally:
        await engine.dispose()


async def _insert_org(factory: async_sessionmaker[AsyncSession], name: str) -> UUID:
    org_id = uuid4()
    slug = f"{name}-{org_id.hex[:8]}"
    async with factory() as session, session.begin():
        await session.execute(text("SELECT set_config('app.is_service_account', 'true', true)"))
        await session.execute(
            text(
                "INSERT INTO ibex_core.organizations (id, name, slug) VALUES "
                "(CAST(:id AS uuid), :name, :slug)"
            ),
            {"id": str(org_id), "name": name, "slug": slug},
        )
    return org_id


async def _cleanup_org(factory: async_sessionmaker[AsyncSession], org_id: UUID) -> None:
    async with factory() as session, session.begin():
        await session.execute(text("SELECT set_config('app.is_service_account', 'true', true)"))
        await session.execute(
            text("DELETE FROM ibex_core.organizations WHERE id = CAST(:id AS uuid)"),
            {"id": str(org_id)},
        )


def _client(org_id: UUID, mgr: FakeTokenManager) -> TestClient:
    settings = Settings(database_url=_require_dsn())
    validator = StaticTokenValidator(
        {"tok": ValidateResult(org_id=org_id, permissions=ADMIN, user_id=str(uuid4()))}
    )
    app = create_app(
        settings=settings,
        validator=validator,
        runtime=ApiRuntimeOverrides(
            token_revoker=NoopTokenRevoker(),
            token_manager=mgr,
            org_suspend_publisher=RecordingOrgSuspendPublisher(),
        ),
    )
    return TestClient(app)


def _assert_not_found(resp) -> None:
    assert resp.status_code == 404, resp.text
    assert resp.json()["error"]["code"] == "NOT_FOUND"


@pytest.mark.asyncio
async def test_api_iso_token_cross_tenant_404(
    factory: async_sessionmaker[AsyncSession],
) -> None:
    """TestAPI_ISO_TOKEN_*: org A cannot GET/DELETE org B token (404)."""
    org_a = await _insert_org(factory, "tok-a")
    org_b = await _insert_org(factory, "tok-b")
    foreign_id = uuid4()
    mgr = FakeTokenManager()
    mgr.seed(
        str(org_b),
        TokenMetadataWire(
            token_id=str(foreign_id),
            name="foreign",
            prefix="ibex_pat_x",
            permissions=MEMORY_READ,
            created_at=datetime.now(UTC),
        ),
    )
    try:
        client = _client(org_a, mgr)
        with client:
            _assert_not_found(client.get(f"/v1/tokens/{foreign_id}", headers=_AUTH))
            _assert_not_found(client.delete(f"/v1/tokens/{foreign_id}", headers=_AUTH))
            listed = client.get("/v1/tokens", headers=_AUTH)
            assert listed.status_code == 200
            assert foreign_id not in {UUID(r["id"]) for r in listed.json()["data"]}
    finally:
        await _cleanup_org(factory, org_a)
        await _cleanup_org(factory, org_b)
