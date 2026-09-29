"""Mounted-route contract tests for authenticated D1 overview reads."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

from authclient.permissions import OPERATOR_METADATA_READ

from app.auth.client import StaticTokenValidator, ValidateResult
from app.deps import operator_org_session
from tests.unit.operator.conftest import create_operator_app, operator_settings


def _session_with_row(org_id: object) -> AsyncMock:
    result = MagicMock()
    result.mappings.return_value.first.return_value = {
        "org_id": org_id,
        "org_name": "Example workspace",
        "org_slug": "example",
        "org_status": "active",
        "role": None,
        "active_users": 2,
        "agents": 3,
        "active_agents": 1,
    }
    session = AsyncMock()
    session.execute = AsyncMock(return_value=result)
    return session


def test_d1_reads_require_a_verified_operator_cookie() -> None:
    with create_operator_app() as (_, client):
        response = client.get("/v1/operator/overview")
    assert response.status_code == 401


def test_d1_reads_require_metadata_permission() -> None:
    validator = StaticTokenValidator(
        {
            "ibex_pat_test_secret": ValidateResult(
                org_id=uuid4(), permissions=0, user_id="u1"
            )
        }
    )
    with create_operator_app(validator=validator) as (_, client):
        login = client.post("/v1/operator/session/login", json={"pat": "ibex_pat_test_secret"})
        assert login.status_code == 200
        response = client.get("/v1/operator/context")
    assert response.status_code == 403


def test_d1_context_and_overview_use_the_authenticated_org_scope() -> None:
    org_id = uuid4()
    validator = StaticTokenValidator(
        {
            "ibex_pat_test_secret": ValidateResult(
                org_id=org_id,
                permissions=OPERATOR_METADATA_READ,
                user_id="u1",
            )
        }
    )
    session = _session_with_row(org_id)
    with create_operator_app(
        settings=operator_settings(), validator=validator
    ) as (app, client):
        app.dependency_overrides[operator_org_session] = lambda: session
        login = client.post("/v1/operator/session/login", json={"pat": "ibex_pat_test_secret"})
        assert login.status_code == 200
        context = client.get("/v1/operator/context")
        overview = client.get("/v1/operator/overview")

    assert context.status_code == 200
    assert context.json()["org_id"] == str(org_id)
    assert context.json()["schema_version"] == "operator.context.v1"
    assert context.json()["role"] is None
    assert context.headers["cache-control"] == "no-store"
    assert not {"subject", "session_id", "permissions", "access_token"} & set(context.json())
    assert overview.status_code == 200
    assert overview.headers["cache-control"] == "no-store"
    assert overview.json()["counts"] == {"active_users": 2, "agents": 3, "active_agents": 1}
    assert session.execute.await_count == 4
    for call in session.execute.await_args_list[::2]:
        assert "statement_timeout" in str(call.args[0])
    for call in session.execute.await_args_list[1::2]:
        assert str(org_id) in repr(call.args) + repr(call.kwargs)
