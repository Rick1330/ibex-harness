"""Integration: agent management ISO 404, lifecycle, slug conflict (live Postgres)."""

from __future__ import annotations

import os
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from dataclasses import dataclass
from uuid import UUID, uuid4

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
_AUTH = {"Authorization": "Bearer tok"}


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


def _client(org_id: UUID, user_id: str) -> TestClient:
    settings = Settings(database_url=_require_dsn())
    validator = StaticTokenValidator(
        {"tok": ValidateResult(org_id=org_id, permissions=ADMIN, user_id=user_id)}
    )
    app = create_app(
        settings=settings,
        validator=validator,
        runtime=ApiRuntimeOverrides(
            token_revoker=NoopTokenRevoker(),
            org_suspend_publisher=RecordingOrgSuspendPublisher(),
        ),
    )
    return TestClient(app)


@dataclass(frozen=True)
class _Tenant:
    org_id: UUID
    user_id: UUID
    slug: str


async def _insert_org_owner(factory: async_sessionmaker[AsyncSession], name: str) -> _Tenant:
    org_id = uuid4()
    user_id = uuid4()
    slug = f"{name}-{org_id.hex[:8]}"
    await _sa(
        factory,
        "INSERT INTO ibex_core.organizations (id, name, slug) VALUES "
        "(CAST(:id AS uuid), :name, :slug)",
        {"id": str(org_id), "name": name, "slug": slug},
    )
    await _sa(
        factory,
        "INSERT INTO ibex_core.users (id, org_id, email, name, role, status) VALUES "
        "(CAST(:id AS uuid), CAST(:org AS uuid), :email, :name, 'owner', 'active')",
        {
            "id": str(user_id),
            "org": str(org_id),
            "email": f"{name}-{org_id.hex[:8]}@example.com",
            "name": f"Owner {name}",
        },
    )
    return _Tenant(org_id=org_id, user_id=user_id, slug=slug)


@dataclass(frozen=True)
class _SeedAgent:
    org_id: UUID
    name: str
    slug: str
    total_sessions: int = 0


async def _insert_agent(factory: async_sessionmaker[AsyncSession], seed: _SeedAgent) -> UUID:
    agent_id = uuid4()
    await _sa(
        factory,
        "INSERT INTO ibex_core.agents (id, org_id, name, slug, total_sessions) VALUES "
        "(CAST(:id AS uuid), CAST(:org AS uuid), :name, :slug, :sessions)",
        {
            "id": str(agent_id),
            "org": str(seed.org_id),
            "name": seed.name,
            "slug": seed.slug,
            "sessions": seed.total_sessions,
        },
    )
    return agent_id


async def _cleanup_orgs(factory: async_sessionmaker[AsyncSession], *org_ids: UUID) -> None:
    for org_id in org_ids:
        await _sa(
            factory,
            "DELETE FROM ibex_core.agents WHERE org_id = CAST(:id AS uuid)",
            {"id": str(org_id)},
        )
        await _sa(
            factory,
            "DELETE FROM ibex_core.users WHERE org_id = CAST(:id AS uuid)",
            {"id": str(org_id)},
        )
        await _sa(
            factory,
            "DELETE FROM ibex_core.organizations WHERE id = CAST(:id AS uuid)",
            {"id": str(org_id)},
        )


@asynccontextmanager
async def _tenants(
    factory: async_sessionmaker[AsyncSession], *names: str
) -> AsyncIterator[list[_Tenant]]:
    seeded = [await _insert_org_owner(factory, n) for n in names]
    try:
        yield seeded
    finally:
        await _cleanup_orgs(factory, *[t.org_id for t in seeded])


def _assert_not_found(resp) -> None:
    assert resp.status_code == 404, resp.text
    assert resp.json()["error"]["code"] == "NOT_FOUND"


def _assert_create_pause_iso(client: TestClient, org: _Tenant, foreign_agent: UUID) -> None:
    slug = f"support-{org.org_id.hex[:8]}"
    created = client.post(
        "/v1/agents",
        headers=_AUTH,
        json={
            "name": "Support",
            "slug": slug,
            "description": "tier-1",
            "default_provider": "openai",
            "default_model": "gpt-4o",
            "tags": ["prod"],
        },
    )
    assert created.status_code == 201, created.text
    body = created.json()
    agent_id = body["id"]
    assert body["default_provider"] == "openai"
    assert body["active_directive_version_id"] is None

    listed = client.get(
        "/v1/agents",
        headers=_AUTH,
        params={"status": "active", "tags": "prod", "search": "Support"},
    )
    assert listed.status_code == 200
    assert any(item["id"] == agent_id for item in listed.json()["data"])

    paused = client.post(f"/v1/agents/{agent_id}/pause", headers=_AUTH)
    assert paused.status_code == 200
    assert paused.json()["status"] == "paused"

    _assert_not_found(client.get(f"/v1/agents/{foreign_agent}", headers=_AUTH))

    conflict = client.post("/v1/agents", headers=_AUTH, json={"name": "Dup", "slug": slug})
    assert conflict.status_code == 409
    assert conflict.json()["error"]["code"] == "AGENT_SLUG_CONFLICT"

    deleted = client.delete(f"/v1/agents/{agent_id}", headers=_AUTH)
    assert deleted.status_code == 204


def _assert_iso_agent_mutations_404(client: TestClient, foreign_agent: UUID) -> None:
    """TestAPI_ISO_AGENT_*: org A cannot modify/delete org B's agent (anti-enumeration 404)."""
    path = f"/v1/agents/{foreign_agent}"
    _assert_not_found(client.patch(path, headers=_AUTH, json={"name": "leaked"}))
    _assert_not_found(client.delete(path, headers=_AUTH))
    for action in ("pause", "activate", "archive"):
        _assert_not_found(client.post(f"{path}/{action}", headers=_AUTH))


@pytest.mark.asyncio
async def test_agent_crud_pause_and_cross_tenant_404(
    factory: async_sessionmaker[AsyncSession],
) -> None:
    async with _tenants(factory, "aga", "agb") as (org_a, org_b):
        foreign = await _insert_agent(
            factory,
            _SeedAgent(org_id=org_b.org_id, name="B Agent", slug=f"b-{org_b.org_id.hex[:8]}"),
        )
        with _client(org_a.org_id, str(org_a.user_id)) as client:
            _assert_create_pause_iso(client, org_a, foreign)


@pytest.mark.asyncio
async def test_api_iso_agent_cross_tenant_mutations_404(
    factory: async_sessionmaker[AsyncSession],
) -> None:
    async with _tenants(factory, "iso-a", "iso-b") as (org_a, org_b):
        foreign = await _insert_agent(
            factory,
            _SeedAgent(
                org_id=org_b.org_id,
                name="Foreign Agent",
                slug=f"foreign-{org_b.org_id.hex[:8]}",
            ),
        )
        with _client(org_a.org_id, str(org_a.user_id)) as client:
            _assert_not_found(client.get(f"/v1/agents/{foreign}", headers=_AUTH))
            _assert_iso_agent_mutations_404(client, foreign)


@pytest.mark.asyncio
async def test_agent_has_sessions_blocks_delete(
    factory: async_sessionmaker[AsyncSession],
) -> None:
    async with _tenants(factory, "sess") as (org,):
        agent_id = await _insert_agent(
            factory,
            _SeedAgent(
                org_id=org.org_id,
                name="Busy",
                slug=f"busy-{org.org_id.hex[:8]}",
                total_sessions=2,
            ),
        )
        with _client(org.org_id, str(org.user_id)) as client:
            resp = client.delete(f"/v1/agents/{agent_id}", headers=_AUTH)
            assert resp.status_code == 409
            assert resp.json()["error"]["code"] == "AGENT_HAS_SESSIONS"
