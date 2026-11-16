"""S02 issuance route: POST /v1/auth/step-up mints a bearer-bound proof.

The proof is the only thing the destructive routes accept as a second factor, so
these tests pin the two properties that make it worth anything: the binding
comes from the verified bearer and never from the body, and every refusal is one
401 with no oracle distinguishing a wrong code from a wrong identity.
"""

from __future__ import annotations

from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch
from uuid import UUID, uuid4

import pytest
from authclient.permissions import ORG_SETTINGS_WRITE, USER_MANAGE
from fastapi.testclient import TestClient

from app.auth.client import AuthFailedError, AuthUnavailableError, ValidateResult
from app.auth.session_refresh import IssuedStepUp, StepUpAttemptLimitError
from app.errors import ApiError
from app.routers.step_up import _bearer_token
from app.step_up import bearer_binding
from tests.unit.org_user_test_support import ApiClientOpts, api_client, bearer_headers

_TOKEN = "owner-token"
_EXPIRES_AT = datetime(2026, 1, 1, 12, 0, tzinfo=UTC)


def _result(
    *,
    user_id: str | None = "user-1",
    token_id: str | None = "tok-1",
    permissions: int = ORG_SETTINGS_WRITE | USER_MANAGE,
    org_id: UUID | None = None,
) -> ValidateResult:
    return ValidateResult(
        org_id=org_id or uuid4(),
        permissions=permissions,
        user_id=user_id,
        token_id=token_id,
    )


def _body(action: str = "org.delete", code: str = "123456") -> dict[str, str]:
    return {"action": action, "code": code}


def _issued(token: str = "proof-1") -> IssuedStepUp:
    return IssuedStepUp(token=token, expires_at=_EXPIRES_AT)


def _client(result: ValidateResult) -> TestClient:
    return api_client(ApiClientOpts(token=_TOKEN, result=result))


def _post(result: ValidateResult, body: dict[str, str] | None = None):
    with _client(result) as (client, _res, _pub):
        return client.post(
            "/v1/auth/step-up",
            json=body if body is not None else _body(),
            headers=bearer_headers(_TOKEN),
        )


def test_issue_step_up_binds_the_proof_to_the_verified_bearer() -> None:
    result = _result()
    rpc = AsyncMock(return_value=_issued())

    with patch("app.routers.step_up.create_step_up", new=rpc):
        resp = _post(result)

    assert resp.status_code == 200
    assert resp.json()["token"] == "proof-1"
    assert resp.json()["expires_at"].startswith("2026-01-01T12:00:00")
    params = rpc.await_args.args[1]
    # The body carries no identity: org, subject and session all come from the
    # bearer the caller already proved it holds.
    assert params.org_id == str(result.org_id)
    assert params.subject == "user-1"
    assert params.session_id == "tok-1"
    assert params.action == "org.delete"
    assert params.code == "123456"
    assert rpc.await_args.kwargs["pat"] == _TOKEN


def test_issue_step_up_binds_a_userless_token_to_its_own_id() -> None:
    """``bearer_binding`` derives both fields from the token id a caller cannot choose.

    Issuance refuses a userless caller (the next test), so this pins the
    derivation itself rather than a proof anyone can obtain with a PAT.
    """
    binding = bearer_binding(_result(user_id=None, token_id="tok-pat"))

    assert binding.subject == "tok-pat"
    assert binding.session_id == "tok-pat"


def test_issue_step_up_refuses_a_userless_token_before_calling_auth() -> None:
    """AuthService issues no proof for a caller with no user id; say so as a 403.

    The only registered action is owner-role gated, and that gate requires a
    user, so a userless PAT could never use the proof. Letting the call through
    would surface AuthService's refusal as an invalid-step-up-code 401.
    """
    rpc = AsyncMock(return_value=_issued())

    with patch("app.routers.step_up.create_step_up", new=rpc):
        resp = _post(_result(user_id=None, token_id="tok-pat"))

    assert resp.status_code == 403
    assert resp.json()["error"]["code"] == "INSUFFICIENT_PERMISSIONS"
    assert resp.json()["error"]["message"] == "User-scoped token required"
    rpc.assert_not_awaited()


def test_issue_step_up_refuses_an_unknown_action_without_calling_auth() -> None:
    rpc = AsyncMock(return_value=_issued())

    with patch("app.routers.step_up.create_step_up", new=rpc):
        resp = _post(_result(), _body(action="org.suspend"))

    assert resp.status_code == 400
    assert resp.json()["error"]["code"] == "INVALID_REQUEST"
    rpc.assert_not_awaited()


def test_issue_step_up_requires_the_permission_the_action_needs() -> None:
    rpc = AsyncMock(return_value=_issued())

    with patch("app.routers.step_up.create_step_up", new=rpc):
        resp = _post(_result(permissions=USER_MANAGE))

    assert resp.status_code == 403
    assert resp.json()["error"]["code"] == "INSUFFICIENT_PERMISSIONS"
    rpc.assert_not_awaited()


def test_issue_step_up_rejects_a_malformed_code() -> None:
    rpc = AsyncMock(return_value=_issued())

    with patch("app.routers.step_up.create_step_up", new=rpc):
        resp = _post(_result(), _body(code="12"))

    assert resp.status_code == 400
    assert resp.json()["error"]["code"] == "VALIDATION_ERROR"
    rpc.assert_not_awaited()


def test_issue_step_up_without_a_bearer_is_401() -> None:
    with _client(_result()) as (client, _res, _pub):
        resp = client.post("/v1/auth/step-up", json=_body())

    assert resp.status_code == 401
    assert resp.json()["error"]["code"] == "MISSING_TOKEN"


def test_issue_step_up_maps_a_refused_code_to_one_401() -> None:
    rpc = AsyncMock(side_effect=AuthFailedError("caller mismatch"))

    with patch("app.routers.step_up.create_step_up", new=rpc):
        resp = _post(_result())

    assert resp.status_code == 401
    assert resp.json()["error"]["code"] == "INVALID_TOKEN"
    assert resp.json()["error"]["message"] == "invalid step-up code"


def test_issue_step_up_maps_the_attempt_limit_to_429() -> None:
    rpc = AsyncMock(side_effect=StepUpAttemptLimitError("attempt limit"))

    with patch("app.routers.step_up.create_step_up", new=rpc):
        resp = _post(_result())

    assert resp.status_code == 429
    assert resp.json()["error"]["code"] == "RATE_LIMITED"


@pytest.mark.parametrize("message", ["auth unavailable", "totp not configured"])
def test_issue_step_up_maps_a_degraded_auth_to_503(message: str) -> None:
    rpc = AsyncMock(side_effect=AuthUnavailableError(message))

    with patch("app.routers.step_up.create_step_up", new=rpc):
        resp = _post(_result())

    assert resp.status_code == 503
    assert resp.json()["error"]["code"] == "SERVICE_DEGRADED"


def test_bearer_token_fails_closed_when_the_header_is_unreadable() -> None:
    """``require_token`` reads the same header first; a rewrite between the two
    reads must not reach AuthService with no caller identity."""
    request = SimpleNamespace(headers={"Authorization": ""})

    with pytest.raises(ApiError) as caught:
        _bearer_token(request)  # type: ignore[arg-type]

    assert caught.value.code == "MISSING_TOKEN"
