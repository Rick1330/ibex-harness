"""Integration: DELETE /v1/users fail-closed when AuthService.RevokeToken is unreachable.

Live auth-cache rejection after a successful revoke loop is covered by
``TestSecurity_SEC7_5_UserDeleteRevokeLoopAuthCache`` in services/proxy
(security-integration CI job). This file asserts the management API does not
soft-delete the user when revoke cannot complete.
"""

from __future__ import annotations

import os
from uuid import uuid4

import pytest
from authclient.permissions import ADMIN, USER_MANAGE
from authclient.revoke import GRPCTokenRevoker
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


async def _scalar(factory: async_sessionmaker[AsyncSession], sql: str, params: dict):
    async with factory() as session, session.begin():
        await session.execute(text("SELECT set_config('app.is_service_account', 'true', true)"))
        result = await session.execute(text(sql), params)
        return result.scalar_one()


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
async def test_delete_user_fails_closed_when_auth_unavailable(
    factory: async_sessionmaker[AsyncSession],
) -> None:
    """DELETE must not soft-delete the user if revoke cannot reach AuthService."""
    org_id = uuid4()
    owner_id = uuid4()
    member_id = uuid4()
    token_id = uuid4()
    slug = f"ua-{org_id.hex[:8]}"
    try:
        await _sa(
            factory,
            "INSERT INTO ibex_core.organizations (id, name, slug) VALUES "
            "(CAST(:id AS uuid), :name, :slug)",
            {"id": str(org_id), "name": "Unavail", "slug": slug},
        )
        await _sa(
            factory,
            "INSERT INTO ibex_core.users (id, org_id, email, name, role, status) VALUES "
            "(CAST(:id AS uuid), CAST(:org AS uuid), :email, :name, 'owner', 'active')",
            {
                "id": str(owner_id),
                "org": str(org_id),
                "email": f"o-{org_id.hex[:8]}@example.com",
                "name": "Owner",
            },
        )
        await _sa(
            factory,
            "INSERT INTO ibex_core.users (id, org_id, email, name, role, status) VALUES "
            "(CAST(:id AS uuid), CAST(:org AS uuid), :email, :name, 'member', 'active')",
            {
                "id": str(member_id),
                "org": str(org_id),
                "email": f"m-{org_id.hex[:8]}@example.com",
                "name": "Member",
            },
        )
        await _sa(
            factory,
            """
            INSERT INTO ibex_core.tokens
                (id, org_id, user_id, type, hash, prefix, name, permissions, is_revoked)
            VALUES (
                CAST(:id AS uuid), CAST(:org AS uuid), CAST(:user AS uuid),
                'pat', 'h', 'ibex_pat_x', 't', 1, false
            )
            """,
            {"id": str(token_id), "org": str(org_id), "user": str(member_id)},
        )

        revoker = GRPCTokenRevoker("127.0.0.1:1", timeout_seconds=0.2)
        settings = Settings(database_url=_require_dsn())
        app = create_app(
            settings=settings,
            validator=StaticTokenValidator(
                {
                    "tok": ValidateResult(
                        org_id=org_id,
                        permissions=ADMIN | USER_MANAGE,
                        user_id=str(owner_id),
                    )
                }
            ),
            runtime=ApiRuntimeOverrides(
                token_revoker=revoker,
                org_suspend_publisher=RecordingOrgSuspendPublisher(),
            ),
        )
        with TestClient(app, raise_server_exceptions=False) as client:
            resp = client.delete(
                f"/v1/users/{member_id}",
                headers={"Authorization": "Bearer tok"},
            )
        assert resp.status_code >= 500
        status = await _scalar(
            factory,
            "SELECT status FROM ibex_core.users WHERE id = CAST(:id AS uuid)",
            {"id": str(member_id)},
        )
        assert status == "active"
        revoked = await _scalar(
            factory,
            "SELECT is_revoked FROM ibex_core.tokens WHERE id = CAST(:id AS uuid)",
            {"id": str(token_id)},
        )
        assert revoked is False
    finally:
        await _sa(
            factory,
            "DELETE FROM ibex_core.tokens WHERE org_id = CAST(:id AS uuid)",
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
