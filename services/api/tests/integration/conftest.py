"""Shared fixtures for API integration tests that need live PostgreSQL."""

from __future__ import annotations

import os
from collections.abc import AsyncIterator, Iterable
from dataclasses import dataclass
from uuid import UUID, uuid4

import pytest
from authclient.permissions import ADMIN, OPERATOR_METADATA_READ
from authclient.revoke import NoopTokenRevoker
from fastapi.testclient import TestClient
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.auth.client import StaticTokenValidator, ValidateResult
from app.config import Settings
from app.db import create_engine, create_session_factory
from app.main import ApiRuntimeOverrides, create_app
from app.revocation_publish import RecordingOrgSuspendPublisher

CURSOR_SECRET = "cursor-secret-32-bytes-minimum!!"
# >=32 bytes: Settings rejects shorter operator HMAC material.
OPERATOR_HMAC_SECRET = "integration-operator-hmac-secret-32b!"
OPERATOR_CURSOR_SECRET = "integration-operator-cursor-secret-32b!"


def require_dsn() -> str:
    dsn = os.environ.get("IBEX_API_DATABASE_URL") or os.environ.get("POSTGRES_TEST_DSN")
    if not dsn:
        pytest.skip("IBEX_API_DATABASE_URL or POSTGRES_TEST_DSN not set")
    return dsn


@pytest.fixture
async def session_factory() -> AsyncIterator[async_sessionmaker[AsyncSession]]:
    engine = create_engine(
        Settings(database_url=require_dsn(), operator_cursor_secret=CURSOR_SECRET)
    )
    factory = create_session_factory(engine)
    try:
        yield factory
    finally:
        await engine.dispose()


SeedStatement = tuple[str, dict[str, object]]

# FK-safe teardown for every row the HTTP tenancy tests may seed. Seeding runs as
# the DSN role (owner/superuser), so no `app.is_service_account` bypass is needed
# or used; migration 000063 replaced that forgeable GUC with `current_user`.
_ORGS_IN = "WHERE org_id IN (CAST(:a AS uuid), CAST(:b AS uuid))"
_TENANT_DELETE_STATEMENTS: tuple[str, ...] = (
    f"DELETE FROM ibex_core.memory_relationships {_ORGS_IN}",
    # Lifecycle events deliberately outlive the organization row (no FK cascade),
    # so they need an explicit delete or they leak as stray rows.
    f"DELETE FROM ibex_core.memory_lifecycle_outbox {_ORGS_IN}",
    f"DELETE FROM ibex_core.memories {_ORGS_IN}",
    f"DELETE FROM ibex_core.checkpoints {_ORGS_IN}",
    f"DELETE FROM ibex_core.evidence_runs {_ORGS_IN}",
    f"DELETE FROM ibex_core.evidence_outbox {_ORGS_IN}",
    # Sessions pin a directive version with ON DELETE RESTRICT; remove them first.
    f"DELETE FROM ibex_core.sessions {_ORGS_IN}",
    f"DELETE FROM ibex_core.directives {_ORGS_IN}",
    f"DELETE FROM ibex_core.directive_versions {_ORGS_IN}",
    # Jobs reference the organization with ON DELETE RESTRICT and take their
    # store receipts with them (receipts cascade on job_id).
    f"DELETE FROM ibex_core.org_deletion_jobs {_ORGS_IN}",
    f"DELETE FROM ibex_core.agents {_ORGS_IN}",
    f"DELETE FROM ibex_core.users {_ORGS_IN}",
    "DELETE FROM ibex_core.organizations WHERE id IN (CAST(:a AS uuid), CAST(:b AS uuid))",
)


@dataclass(frozen=True)
class TwoTenantOperator:
    """Two logged-in operator clients, each bound to its own organization.

    ``factory`` is an owner-DSN session factory: tests seed and clean up rows
    outside the application's RLS-bound ``ibex_app`` session.
    """

    org_a: UUID
    org_b: UUID
    user_a: UUID
    user_b: UUID
    org_a_name: str
    org_b_name: str
    org_a_slug: str
    org_b_slug: str
    pat_a: str
    pat_b: str
    client_a: TestClient
    client_b: TestClient
    factory: async_sessionmaker[AsyncSession]

    async def seed(self, statements: Iterable[SeedStatement]) -> None:
        """Insert fixture rows in one owner transaction (no tenant GUC)."""
        async with self.factory() as session, session.begin():
            for sql, params in statements:
                await session.execute(text(sql), params)


def _operator_settings() -> Settings:
    return Settings(
        database_url=require_dsn(),
        environment="development",
        operator_feature_enabled=True,
        jwt_hmac_secret=OPERATOR_HMAC_SECRET,
        operator_cursor_secret=OPERATOR_CURSOR_SECRET,
        cookie_secure=False,
        cookie_samesite="lax",
    )


def _operator_client(org_id: UUID, user_id: UUID, pat: str) -> TestClient:
    validator = StaticTokenValidator(
        {
            pat: ValidateResult(
                org_id=org_id,
                permissions=ADMIN | OPERATOR_METADATA_READ,
                user_id=str(user_id),
            )
        }
    )
    app = create_app(
        settings=_operator_settings(),
        validator=validator,
        runtime=ApiRuntimeOverrides(
            token_revoker=NoopTokenRevoker(),
            org_suspend_publisher=RecordingOrgSuspendPublisher(),
        ),
    )
    return TestClient(app)


def _login(client: TestClient, pat: str, org_id: UUID) -> None:
    response = client.post("/v1/operator/session/login", json={"pat": pat})
    assert response.status_code == 200, response.text
    assert response.json()["org_id"] == str(org_id)


async def _seed_tenant_identities(
    factory: async_sessionmaker[AsyncSession],
    tenants: list[tuple[UUID, UUID, str, str, str]],
) -> None:
    async with factory() as session, session.begin():
        for org_id, user_id, name, slug, email in tenants:
            await session.execute(
                text(
                    "INSERT INTO ibex_core.organizations (id, name, slug) "
                    "VALUES (CAST(:id AS uuid), :name, :slug)"
                ),
                {"id": str(org_id), "name": name, "slug": slug},
            )
            await session.execute(
                text(
                    "INSERT INTO ibex_core.users (id, org_id, email, name, role, status) "
                    "VALUES (CAST(:id AS uuid), CAST(:org AS uuid), :email, :name, "
                    "'owner', 'active')"
                ),
                {
                    "id": str(user_id),
                    "org": str(org_id),
                    "email": email,
                    "name": f"Owner {name}",
                },
            )


async def _cleanup_tenants(
    factory: async_sessionmaker[AsyncSession], org_a: UUID, org_b: UUID
) -> None:
    targets = {"a": str(org_a), "b": str(org_b)}
    async with factory() as session, session.begin():
        for statement in _TENANT_DELETE_STATEMENTS:
            await session.execute(text(statement), targets)


@pytest.fixture
async def two_tenant_operator() -> AsyncIterator[TwoTenantOperator]:
    """Two orgs, two users, two PATs, two cookie sessions, and an owner seeder.

    Each ``TestClient`` is a separate app instance whose only accepted PAT maps
    to one org; ``POST /v1/operator/session/login`` exchanges it for the operator
    session cookie, so requests after login carry the cookie-bound org rather
    than the PAT.
    """
    engine = create_engine(Settings(database_url=require_dsn()))
    factory = create_session_factory(engine)
    suffix = uuid4().hex[:12]
    org_a, org_b = uuid4(), uuid4()
    user_a, user_b = uuid4(), uuid4()
    org_a_name, org_b_name = f"Tenant Alpha {suffix}", f"Tenant Bravo {suffix}"
    org_a_slug, org_b_slug = f"tenancy-http-a-{suffix}", f"tenancy-http-b-{suffix}"
    pat_a, pat_b = f"ibex_pat_tenancy_a_{suffix}", f"ibex_pat_tenancy_b_{suffix}"
    try:
        await _seed_tenant_identities(
            factory,
            [
                (org_a, user_a, org_a_name, org_a_slug, f"alpha-{suffix}@example.test"),
                (org_b, user_b, org_b_name, org_b_slug, f"bravo-{suffix}@example.test"),
            ],
        )
        with (
            _operator_client(org_a, user_a, pat_a) as client_a,
            _operator_client(org_b, user_b, pat_b) as client_b,
        ):
            _login(client_a, pat_a, org_a)
            _login(client_b, pat_b, org_b)
            yield TwoTenantOperator(
                org_a=org_a,
                org_b=org_b,
                user_a=user_a,
                user_b=user_b,
                org_a_name=org_a_name,
                org_b_name=org_b_name,
                org_a_slug=org_a_slug,
                org_b_slug=org_b_slug,
                pat_a=pat_a,
                pat_b=pat_b,
                client_a=client_a,
                client_b=client_b,
                factory=factory,
            )
    finally:
        await _cleanup_tenants(factory, org_a, org_b)
        await engine.dispose()
