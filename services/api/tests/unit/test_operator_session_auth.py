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
from app.operator_session_auth import _verified_local_session, require_operator_session


def _request(settings: Settings, token: str = "opaque") -> Request:
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
        "headers": [(b"cookie", f"ibex_session={token}".encode())],
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
    with patch("app.operator_session_auth.verify_token_opts", return_value=claims):
        with pytest.raises(ApiError) as exc:
            _verified_local_session("token", settings)
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
    with patch(
        "app.operator_session_auth.validate_operator_session", return_value=incomplete
    ):
        with pytest.raises(ApiError) as exc:
            asyncio.run(pending)
    assert exc.value.code == INVALID_TOKEN
    assert exc.value.message == "incomplete session claims"
