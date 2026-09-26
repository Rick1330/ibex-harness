from __future__ import annotations

import asyncio
from types import SimpleNamespace
from unittest.mock import patch
from uuid import uuid4

import pytest
from apierror_py import INVALID_TOKEN
from starlette.applications import Starlette
from starlette.requests import Request

from app.auth.session_refresh import ValidatedSession
from app.config import Settings
from app.errors import ApiError
from app.operator_session_auth import (
    OperatorSessionAuthorization,
    _verified_local_session,
    require_operator_session,
)


def _request(settings: Settings, token: str | None = "opaque") -> Request:
    app = Starlette()
    app.state.settings = settings
    scope = {
        "type": "http",
        "asgi": {"version": "3.0"},
        "http_version": "1.1",
        "method": "GET",
        "scheme": "http",
        "path": "/",
        "raw_path": b"/",
        "query_string": b"",
        "headers": [] if token is None else [(b"cookie", f"ibex_session={token}".encode())],
        "client": ("127.0.0.1", 123),
        "server": ("test", 80),
        "app": app,
    }
    return Request(scope)


def _settings(**overrides: object) -> Settings:
    values: dict[str, object] = {
        "environment": "development",
        "operator_feature_enabled": True,
        "jwt_hmac_secret": "h" * 32,
        "jwt_public_keys_pem": None,
        "jwt_issuer": "ibex-harness",
        "jwt_audience": "ibex-dashboard",
        "dashboard_session_cookie_name": "ibex_session",
        "auth_grpc_addr": "127.0.0.1:50051",
        "auth_timeout_ms": 100,
    }
    values.update(overrides)
    return Settings.model_construct(**values)


def test_local_operator_session_rejects_non_uuid_org_context() -> None:
    settings = _settings()
    claims = SimpleNamespace(org_id="not-a-uuid", permissions=0, session_id="sid")
    patched = patch("app.operator_session_auth.verify_token_opts", return_value=claims)
    patched.start()
    try:
        with pytest.raises(ApiError) as exc:
            _verified_local_session("token", settings)
    finally:
        patched.stop()
    assert exc.value.code == INVALID_TOKEN
    assert exc.value.message == "missing org context in session"


def test_authservice_operator_session_rejects_incomplete_verified_claims() -> None:
    settings = _settings(
        environment="staging",
        jwt_hmac_secret=None,
        jwt_public_keys_pem="configured-public-key",
    )
    incomplete = ValidatedSession(
        subject="", org_id=str(uuid4()), permissions=0, session_id="sid", jti="jti"
    )
    pending = require_operator_session(_request(settings))
    patched = patch(
        "app.operator_session_auth.validate_operator_session", return_value=incomplete
    )
    patched.start()
    try:
        with pytest.raises(ApiError) as exc:
            asyncio.run(pending)
    finally:
        patched.stop()
    assert exc.value.code == INVALID_TOKEN
    assert exc.value.message == "incomplete session claims"


def test_local_operator_session_binds_verified_identity_to_request_state() -> None:
    settings = _settings()
    authorization = OperatorSessionAuthorization(
        org_id=uuid4(), permissions=7, session_id="sid", subject="user-1"
    )
    request = _request(settings)
    with patch(
        "app.operator_session_auth._verified_local_session",
        return_value=authorization,
    ):
        result = asyncio.run(require_operator_session(request))
    assert result is authorization
    assert request.state.ibex_session_org_id == str(authorization.org_id)
    assert request.state.ibex_session_sub == "user-1"
    assert request.state.ibex_session_id == "sid"


def test_local_operator_session_rejects_missing_subject() -> None:
    settings = _settings()
    request = _request(settings)
    authorization = OperatorSessionAuthorization(
        org_id=uuid4(), permissions=7, session_id="sid", subject=""
    )
    with patch(
        "app.operator_session_auth._verified_local_session",
        return_value=authorization,
    ), pytest.raises(ApiError) as exc:
        asyncio.run(require_operator_session(request))
    assert exc.value.code == INVALID_TOKEN
    assert exc.value.message == "missing session subject"


@pytest.mark.parametrize(
    ("overrides", "message"),
    [
        ({"operator_feature_enabled": False}, "operator feature disabled"),
        ({"jwt_hmac_secret": None, "jwt_public_keys_pem": None}, "session verification key not configured"),
    ],
)
def test_operator_session_rejects_unavailable_local_configuration(
    overrides: dict[str, object], message: str
) -> None:
    with pytest.raises(ApiError, match=message):
        asyncio.run(require_operator_session(_request(_settings(**overrides))))


def test_operator_session_rejects_missing_cookie() -> None:
    with pytest.raises(ApiError, match="missing session cookie"):
        asyncio.run(require_operator_session(_request(_settings(), token=None)))


def test_local_operator_session_rejects_token_verification_error() -> None:
    from app.session_stub import SessionStubError

    with patch(
        "app.operator_session_auth.verify_token_opts",
        side_effect=SessionStubError("expired"),
    ), pytest.raises(ApiError, match="expired"):
        _verified_local_session("token", _settings())


def test_local_operator_session_rejects_missing_org_claim() -> None:
    claims = SimpleNamespace(org_id=None, permissions=0, session_id="sid", sub="user")
    with (
        patch("app.operator_session_auth.verify_token_opts", return_value=claims),
        pytest.raises(ApiError, match="missing org context"),
    ):
        _verified_local_session("token", _settings())


def test_local_operator_session_builds_authorization() -> None:
    org = uuid4()
    claims = SimpleNamespace(org_id=org, permissions=7, session_id="sid", sub="user")
    with patch("app.operator_session_auth.verify_token_opts", return_value=claims):
        result = _verified_local_session("token", _settings())
    assert result.org_id == org
    assert result.permissions == 7
    assert result.session_id == "sid"
    assert result.subject == "user"


@pytest.mark.parametrize(
    "error",
    [
        Exception("invalid"),
        ValueError("bad target"),
        RuntimeError("auth down"),
    ],
)
def test_remote_operator_session_maps_auth_errors(error: Exception) -> None:
    from app.auth.client import AuthFailedError
    from app.auth.errors import AuthUnavailableError

    if isinstance(error, Exception) and str(error) == "invalid":
        error = AuthFailedError("invalid")
    elif isinstance(error, Exception) and str(error) == "auth down":
        error = AuthUnavailableError("down")
    settings = _settings(
        environment="staging", jwt_hmac_secret=None, jwt_public_keys_pem="public"
    )
    with patch(
        "app.operator_session_auth.validate_operator_session", side_effect=error
    ), pytest.raises(ApiError) as exc:
        asyncio.run(require_operator_session(_request(settings)))
    assert exc.value.code in {"INVALID_TOKEN", "SERVICE_DEGRADED"}


def test_validated_session_claims_build_authorization() -> None:
    from app.operator_session_auth import _authorization_from_validated

    claims = ValidatedSession(
        subject="user-1", org_id=str(uuid4()), permissions=7, session_id="sid", jti="jti"
    )
    result = _authorization_from_validated(claims)
    assert result.subject == "user-1"
    assert result.session_id == "sid"


@pytest.mark.parametrize("missing", ["session_id", "jti"])
def test_validated_session_claims_require_all_identifiers(missing: str) -> None:
    from app.operator_session_auth import _require_complete_session_claims

    values = {"subject": "user", "session_id": "sid", "jti": "jti"}
    values[missing] = ""
    claims = ValidatedSession(org_id=str(uuid4()), permissions=0, **values)
    with pytest.raises(ApiError, match="incomplete session claims"):
        _require_complete_session_claims(claims)


def test_validated_session_claims_reject_invalid_org_id() -> None:
    from app.operator_session_auth import _authorization_from_validated

    claims = ValidatedSession(
        subject="user", org_id="not-a-uuid", permissions=0, session_id="sid", jti="jti"
    )
    with pytest.raises(ApiError, match="missing org context"):
        _authorization_from_validated(claims)
