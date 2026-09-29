"""Integration: D1 Overview reads honor the verified organization GUC and RLS."""

from __future__ import annotations

import os
from dataclasses import dataclass
from uuid import UUID, uuid4

import pytest
from apierror_py import NOT_FOUND
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.config import Settings
from app.db import create_engine, create_session_factory, session_with_org
from app.errors import ApiError
from app.operator_session_auth import OperatorSessionAuthorization
from app.services.operator_overview import get_operator_d1_read_model

pytestmark = pytest.mark.integration


def _require_dsn() -> str:
    dsn = os.environ.get("IBEX_API_DATABASE_URL") or os.environ.get("POSTGRES_TEST_DSN")
    if not dsn:
        pytest.skip("IBEX_API_DATABASE_URL or POSTGRES_TEST_DSN not set")
    return dsn


@pytest.fixture
async def session_factory() -> async_sessionmaker[AsyncSession]:
    engine = create_engine(Settings(database_url=_require_dsn()))
    factory = create_session_factory(engine)
    try:
        yield factory
    finally:
        await engine.dispose()


@dataclass(frozen=True)
class _UserSeed:
    user_id: UUID
    org_id: UUID
    email: str
    name: str
    role: str


@dataclass(frozen=True)
class _AgentSeed:
    agent_id: UUID
    org_id: UUID
    slug: str
    status: str
    deleted: bool


@dataclass(frozen=True)
class _TenantFixture:
    org_a: UUID
    org_b: UUID
    user_a: UUID
    user_b: UUID
    agent_a_active: UUID
    agent_a_paused: UUID
    agent_a_deleted: UUID
    agent_b: UUID
    suffix: str


async def _seed_organization(session: AsyncSession, org_id: UUID, name: str) -> None:
    await session.execute(
        text(
            "INSERT INTO ibex_core.organizations (id, name, slug) "
            "VALUES (CAST(:id AS uuid), :name, :slug)"
        ),
        {"id": str(org_id), "name": name, "slug": f"d1-rls-{org_id.hex}"},
    )


async def _seed_user(session: AsyncSession, seed: _UserSeed) -> None:
    await session.execute(
        text(
            "INSERT INTO ibex_core.users (id, org_id, email, name, role, status) "
            "VALUES (CAST(:id AS uuid), CAST(:org_id AS uuid), :email, :name, :role, 'active')"
        ),
        {
            "id": str(seed.user_id),
            "org_id": str(seed.org_id),
            "email": seed.email,
            "name": seed.name,
            "role": seed.role,
        },
    )


async def _seed_non_live_users(session: AsyncSession, org_id: UUID, suffix: str) -> None:
    await session.execute(
        text(
            "INSERT INTO ibex_core.users (org_id, email, name, status) "
            "VALUES (CAST(:org_id AS uuid), :email, 'Invited D1 user', 'invited'), "
            "       (CAST(:org_id AS uuid), :deleted_email, 'Deleted D1 user', 'active')"
        ),
        {
            "org_id": str(org_id),
            "email": f"{suffix}-invited@example.test",
            "deleted_email": f"{suffix}-deleted@example.test",
        },
    )
    await session.execute(
        text(
            "UPDATE ibex_core.users SET deleted_at = NOW() "
            "WHERE org_id = CAST(:org_id AS uuid) AND email = :email"
        ),
        {"org_id": str(org_id), "email": f"{suffix}-deleted@example.test"},
    )


async def _seed_agent(session: AsyncSession, seed: _AgentSeed, suffix: str) -> None:
    await session.execute(
        text(
            "INSERT INTO ibex_core.agents (id, org_id, name, slug, status, deleted_at) "
            "VALUES (CAST(:id AS uuid), CAST(:org_id AS uuid), :name, :slug, :status, "
            "CASE WHEN :deleted THEN NOW() ELSE NULL END)"
        ),
        {
            "id": str(seed.agent_id),
            "org_id": str(seed.org_id),
            "name": f"D1 agent {seed.slug}",
            "slug": f"{suffix}-{seed.slug}",
            "status": seed.status,
            "deleted": seed.deleted,
        },
    )


async def _seed_d1_tenants(session: AsyncSession, fixture: _TenantFixture) -> None:
    await _seed_organization(session, fixture.org_a, "D1 RLS A")
    await _seed_organization(session, fixture.org_b, "D1 RLS B")
    await _seed_user(
        session,
        _UserSeed(
            user_id=fixture.user_a,
            org_id=fixture.org_a,
            email=f"{fixture.suffix}-{fixture.user_a.hex}@example.test",
            name=f"D1 user {fixture.user_a.hex[:8]}",
            role="admin",
        ),
    )
    await _seed_user(
        session,
        _UserSeed(
            user_id=fixture.user_b,
            org_id=fixture.org_b,
            email=f"{fixture.suffix}-{fixture.user_b.hex}@example.test",
            name=f"D1 user {fixture.user_b.hex[:8]}",
            role="owner",
        ),
    )
    await _seed_non_live_users(session, fixture.org_a, fixture.suffix)
    for seed in (
        _AgentSeed(fixture.agent_a_active, fixture.org_a, "active", "active", False),
        _AgentSeed(fixture.agent_a_paused, fixture.org_a, "paused", "paused", False),
        _AgentSeed(fixture.agent_a_deleted, fixture.org_a, "deleted", "active", True),
        _AgentSeed(fixture.agent_b, fixture.org_b, "other-tenant", "active", False),
    ):
        await _seed_agent(session, seed, fixture.suffix)


async def _cleanup_d1_tenants(
    session_factory: async_sessionmaker[AsyncSession],
    org_a: UUID,
    org_b: UUID,
) -> None:
    async with session_factory() as cleanup, cleanup.begin():
        await cleanup.execute(
            text("DELETE FROM ibex_core.agents WHERE org_id IN (CAST(:a AS uuid), CAST(:b AS uuid))"),
            {"a": str(org_a), "b": str(org_b)},
        )
        await cleanup.execute(
            text("DELETE FROM ibex_core.users WHERE org_id IN (CAST(:a AS uuid), CAST(:b AS uuid))"),
            {"a": str(org_a), "b": str(org_b)},
        )
        await cleanup.execute(
            text("DELETE FROM ibex_core.organizations WHERE id IN (CAST(:a AS uuid), CAST(:b AS uuid))"),
            {"a": str(org_a), "b": str(org_b)},
        )


@pytest.mark.asyncio
async def test_d1_read_model_is_tenant_scoped_and_counts_only_live_rows(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    fixture = _TenantFixture(
        org_a=uuid4(),
        org_b=uuid4(),
        user_a=uuid4(),
        user_b=uuid4(),
        agent_a_active=uuid4(),
        agent_a_paused=uuid4(),
        agent_a_deleted=uuid4(),
        agent_b=uuid4(),
        suffix=uuid4().hex,
    )

    try:
        async with session_factory() as session, session.begin():
            await _seed_d1_tenants(session, fixture)

        authorization_a = OperatorSessionAuthorization(
            org_id=fixture.org_a,
            permissions=1,
            session_id="integration-session-a",
            subject=str(fixture.user_a),
        )
        authorization_b = OperatorSessionAuthorization(
            org_id=fixture.org_b,
            permissions=1,
            session_id="integration-session-b",
            subject=str(fixture.user_b),
        )
        async with session_with_org(session_factory, str(fixture.org_a)) as session:
            context, overview = await get_operator_d1_read_model(session, authorization_a)
            assert context.org_id == fixture.org_a
            assert context.role == "admin"
            assert overview.counts.model_dump() == {
                "active_users": 1,
                "agents": 2,
                "active_agents": 1,
            }

            with pytest.raises(ApiError) as error:
                await get_operator_d1_read_model(session, authorization_b)
            assert error.value.code == NOT_FOUND
            assert "D1 RLS B" not in str(error.value)
    finally:
        await _cleanup_d1_tenants(session_factory, fixture.org_a, fixture.org_b)
