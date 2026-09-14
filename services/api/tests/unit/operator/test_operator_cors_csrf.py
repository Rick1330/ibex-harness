"""CORS and CSRF enforcement."""

from __future__ import annotations

from starlette.applications import Starlette

from app.middleware.cors import build_cors_middleware


def test_cors_allows_listed_origin(app_client) -> None:
    _, client = app_client
    resp = client.options(
        "/health",
        headers={
            "Origin": "http://localhost:3100",
            "Access-Control-Request-Method": "GET",
        },
    )
    assert resp.status_code == 200
    assert resp.headers.get("access-control-allow-origin") == "http://localhost:3100"
    assert resp.headers.get("access-control-allow-credentials") == "true"


def test_cors_rejects_disallowed_origin(app_client) -> None:
    _, client = app_client
    resp = client.options(
        "/health",
        headers={
            "Origin": "https://evil.example",
            "Access-Control-Request-Method": "GET",
        },
    )
    assert resp.headers.get("access-control-allow-origin") != "https://evil.example"
    assert resp.headers.get("access-control-allow-origin") in (None, "null", "")


def test_csrf_rejects_missing_token_on_cookie_mutation(app_client) -> None:
    _, client = app_client
    login = client.post("/v1/operator/session/login", json={"pat": "ibex_pat_test_secret"})
    assert login.status_code == 200
    resp = client.post("/v1/operator/events/publish-test", json={"hello": "world"})
    assert resp.status_code == 403
    assert resp.json()["error"]["code"] == "csrf_failed"


def test_csrf_rejects_mismatched_token(app_client) -> None:
    _, client = app_client
    login = client.post("/v1/operator/session/login", json={"pat": "ibex_pat_test_secret"})
    assert login.status_code == 200
    resp = client.post(
        "/v1/operator/events/publish-test",
        json={"hello": "world"},
        headers={"X-CSRF-Token": "not-the-cookie-value"},
    )
    assert resp.status_code == 403
    assert resp.json()["error"]["code"] == "csrf_failed"


def test_csrf_accepts_matching_double_submit(app_client) -> None:
    _, client = app_client
    login = client.post("/v1/operator/session/login", json={"pat": "ibex_pat_test_secret"})
    assert login.status_code == 200
    csrf = login.json()["csrf_token"]
    resp = client.post(
        "/v1/operator/events/publish-test",
        json={"hello": "world"},
        headers={"X-CSRF-Token": csrf},
    )
    assert resp.status_code == 200
    assert resp.json()["event_id"] >= 1


def test_csrf_misconfigured_without_secret() -> None:
    from unittest.mock import AsyncMock, MagicMock, patch
    from uuid import uuid4

    from fastapi.testclient import TestClient

    from app.auth.client import StaticTokenValidator, ValidateResult
    from app.config import Settings
    from app.main import create_app
    from tests.unit.operator.conftest import HMAC_SECRET, mock_engine

    settings = Settings(
        database_url="postgresql+asyncpg://ibex:ibex@127.0.0.1:5432/ibex",
        allowed_origins="http://localhost:3100",
        jwt_hmac_secret=HMAC_SECRET,
        dashboard_csrf_secret=None,
        cookie_secure=False,
        operator_feature_enabled=True,
    )
    validator = StaticTokenValidator(
        {"ibex_pat_test_secret": ValidateResult(org_id=uuid4(), permissions=1, user_id="u1")}
    )
    with (
        patch("app.main.create_engine", return_value=mock_engine()),
        patch("app.main.create_session_factory", return_value=MagicMock()),
        patch("authclient.revoke.GRPCTokenRevoker", return_value=MagicMock(aclose=AsyncMock())),
        patch("authclient.tokens.GRPCTokenManager", return_value=MagicMock(aclose=AsyncMock())),
        patch(
            "authclient.provider_credentials.GRPCProviderCredentialManager",
            return_value=MagicMock(aclose=AsyncMock()),
        ),
    ):
        app = create_app(settings=settings, validator=validator)
        with TestClient(app) as client:
            login = client.post("/v1/operator/session/login", json={"pat": "ibex_pat_test_secret"})
            assert login.status_code == 200
            resp = client.post("/v1/operator/events/publish-test", json={"x": 1})
            assert resp.status_code == 503
            assert resp.json()["error"]["code"] == "csrf_misconfigured"


def test_csrf_required_when_only_refresh_cookie(app_client) -> None:
    _, client = app_client
    login = client.post("/v1/operator/session/login", json={"pat": "ibex_pat_test_secret"})
    assert login.status_code == 200
    # Drop access cookie; keep refresh — CSRF must still apply.
    client.cookies.pop("ibex_session", None)
    resp = client.post("/v1/operator/session/refresh")
    assert resp.status_code == 403
    assert resp.json()["error"]["code"] == "csrf_failed"


def test_build_cors_middleware_strips_star() -> None:
    mw = build_cors_middleware(Starlette(), allow_origins=["http://localhost:3100", "*"])
    assert "http://localhost:3100" in mw.allow_origins
    assert "*" not in mw.allow_origins
