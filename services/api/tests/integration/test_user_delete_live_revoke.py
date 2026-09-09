"""Integration: DELETE /v1/users fail-closed when AuthService.RevokeToken is unreachable.

Live auth-cache rejection after a successful revoke loop is covered by
``TestSecurity_SEC7_5_UserDeleteRevokeLoopAuthCache`` in services/proxy
(security-integration CI job). This file asserts the management API does not
soft-delete the user when revoke cannot complete.
"""

from __future__ import annotations

import os
from collections.abc import AsyncIterator
from dataclasses import dataclass
from uuid import UUID, uuid4

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
async def factory() -> AsyncIterator[async_sessionmaker[AsyncSession]]:
    settings = Settings(database_url=_require_dsn())
    engine = create_engine(settings)
    fac = create_session_factory(engine)
    try:
        yield fac
    finally:
        await engine.dispose()


@dataclass(frozen=True)
class _SeededOrg:
    org_id: UUID
    owner_id: UUID
    member_id: UUID
    token_id: UUID


async def _seed_org_with_member_pat(factory: async_sessionmaker[AsyncSession]) -> _SeededOrg:
    seeded = _SeededOrg(org_id=uuid4(), owner_id=uuid4(), member_id=uuid4(), token_id=uuid4())
    slug = f"ua-{seeded.org_id.hex[:8]}"
    await _sa(
        factory,
        "INSERT INTO ibex_core.organizations (id, name, slug) VALUES "
        "(CAST(:id AS uuid), :name, :slug)",
        {"id": str(seeded.org_id), "name": "Unavail", "slug": slug},
    )
    for user_id, email_prefix, role in (
        (seeded.owner_id, "o", "owner"),
        (seeded.member_id, "m", "member"),
    ):
        await _sa(
            factory,
            "INSERT INTO ibex_core.users (id, org_id, email, name, role, status) VALUES "
            "(CAST(:id AS uuid), CAST(:org AS uuid), :email, :name, :role, 'active')",
            {
                "id": str(user_id),
                "org": str(seeded.org_id),
                "email": f"{email_prefix}-{seeded.org_id.hex[:8]}@example.com",
                "name": role.title(),
                "role": role,
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
        {
            "id": str(seeded.token_id),
            "org": str(seeded.org_id),
            "user": str(seeded.member_id),
        },
    )
    return seeded


async def _cleanup_org(factory: async_sessionmaker[AsyncSession], org_id: UUID) -> None:
    oid = {"id": str(org_id)}
    await _sa(factory, "DELETE FROM ibex_core.tokens WHERE org_id = CAST(:id AS uuid)", oid)
    await _sa(factory, "DELETE FROM ibex_core.users WHERE org_id = CAST(:id AS uuid)", oid)
    await _sa(factory, "DELETE FROM ibex_core.organizations WHERE id = CAST(:id AS uuid)", oid)


def _delete_member_with_dead_auth(seeded: _SeededOrg) -> int:
    revoker = GRPCTokenRevoker("127.0.0.1:1", timeout_seconds=0.2)
    app = create_app(
        settings=Settings(database_url=_require_dsn()),
        validator=StaticTokenValidator(
            {
                "tok": ValidateResult(
                    org_id=seeded.org_id,
                    permissions=ADMIN | USER_MANAGE,
                    user_id=str(seeded.owner_id),
                )
            }
        ),
        runtime=ApiRuntimeOverrides(
            token_revoker=revoker,
            org_suspend_publisher=RecordingOrgSuspendPublisher(),
        ),
    )
    with TestClient(app, raise_server_exceptions=False) as client:
        return client.delete(
            f"/v1/users/{seeded.member_id}",
            headers={"Authorization": "Bearer tok"},
        ).status_code


@pytest.mark.asyncio
async def test_delete_user_fails_closed_when_auth_unavailable(
    factory: async_sessionmaker[AsyncSession],
) -> None:
    """DELETE must not soft-delete the user if revoke cannot reach AuthService."""
    seeded = await _seed_org_with_member_pat(factory)
    try:
        assert _delete_member_with_dead_auth(seeded) >= 500
        status = await _scalar(
            factory,
            "SELECT status FROM ibex_core.users WHERE id = CAST(:id AS uuid)",
            {"id": str(seeded.member_id)},
        )
        assert status == "active"
        revoked = await _scalar(
            factory,
            "SELECT is_revoked FROM ibex_core.tokens WHERE id = CAST(:id AS uuid)",
            {"id": str(seeded.token_id)},
        )
        assert revoked is False
    finally:
        await _cleanup_org(factory, seeded.org_id)
