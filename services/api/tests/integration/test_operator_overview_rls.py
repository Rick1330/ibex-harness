"""Integration: D1 Overview reads honor the verified organization GUC and RLS."""

from __future__ import annotations

import os
from uuid import uuid4

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


@pytest.mark.asyncio
async def test_d1_read_model_is_tenant_scoped_and_counts_only_live_rows(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    org_a, org_b = uuid4(), uuid4()
    user_a, user_b = uuid4(), uuid4()
    agent_a_active, agent_a_paused, agent_a_deleted, agent_b = (uuid4() for _ in range(4))
    suffix = uuid4().hex

    try:
        async with session_factory() as session, session.begin():
            for org_id, name in ((org_a, "D1 RLS A"), (org_b, "D1 RLS B")):
                await session.execute(
                    text(
                        "INSERT INTO ibex_core.organizations (id, name, slug) "
                        "VALUES (CAST(:id AS uuid), :name, :slug)"
                    ),
                    {"id": str(org_id), "name": name, "slug": f"d1-rls-{org_id.hex}"},
                )
            for user_id, org_id, role in (
                (user_a, org_a, "admin"),
                (user_b, org_b, "owner"),
            ):
                await session.execute(
                    text(
                        "INSERT INTO ibex_core.users (id, org_id, email, name, role, status) "
                        "VALUES (CAST(:id AS uuid), CAST(:org_id AS uuid), :email, :name, :role, 'active')"
                    ),
                    {
                        "id": str(user_id),
                        "org_id": str(org_id),
                        "email": f"{suffix}-{user_id.hex}@example.test",
                        "name": f"D1 user {user_id.hex[:8]}",
                        "role": role,
                    },
                )
            await session.execute(
                text(
                    "INSERT INTO ibex_core.users (org_id, email, name, status) "
                    "VALUES (CAST(:org_id AS uuid), :email, 'Invited D1 user', 'invited'), "
                    "       (CAST(:org_id AS uuid), :deleted_email, 'Deleted D1 user', 'active')"
                ),
                {
                    "org_id": str(org_a),
                    "email": f"{suffix}-invited@example.test",
                    "deleted_email": f"{suffix}-deleted@example.test",
                },
            )
            await session.execute(
                text(
                    "UPDATE ibex_core.users SET deleted_at = NOW() "
                    "WHERE org_id = CAST(:org_id AS uuid) AND email = :email"
                ),
                {"org_id": str(org_a), "email": f"{suffix}-deleted@example.test"},
            )
            for agent_id, org_id, slug, status, deleted in (
                (agent_a_active, org_a, "active", "active", False),
                (agent_a_paused, org_a, "paused", "paused", False),
                (agent_a_deleted, org_a, "deleted", "active", True),
                (agent_b, org_b, "other-tenant", "active", False),
            ):
                await session.execute(
                    text(
                        "INSERT INTO ibex_core.agents (id, org_id, name, slug, status, deleted_at) "
                        "VALUES (CAST(:id AS uuid), CAST(:org_id AS uuid), :name, :slug, :status, "
                        "CASE WHEN :deleted THEN NOW() ELSE NULL END)"
                    ),
                    {
                        "id": str(agent_id),
                        "org_id": str(org_id),
                        "name": f"D1 agent {slug}",
                        "slug": f"{suffix}-{slug}",
                        "status": status,
                        "deleted": deleted,
                    },
                )

        authorization_a = OperatorSessionAuthorization(
            org_id=org_a,
            permissions=1,
            session_id="integration-session-a",
            subject=str(user_a),
        )
        authorization_b = OperatorSessionAuthorization(
            org_id=org_b,
            permissions=1,
            session_id="integration-session-b",
            subject=str(user_b),
        )
        async with session_with_org(session_factory, str(org_a)) as session:
            context, overview = await get_operator_d1_read_model(session, authorization_a)
            assert context.org_id == org_a
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
