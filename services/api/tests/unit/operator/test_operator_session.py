"""Operator session stub routes."""

from __future__ import annotations

from unittest.mock import AsyncMock, patch
from uuid import uuid4

import pytest

from app.auth.client import StaticTokenValidator, ValidateResult
from app.config import Settings
from app.session_stub import (
    SESSION_KIND_ACCESS,
    SESSION_KIND_REFRESH,
    SessionStubError,
    TokenIssueOpts,
    TokenVerifyOpts,
    issue_token_opts,
    mint_csrf_token,
    verify_csrf_token,
    verify_token_opts,
)
from tests.unit.operator.conftest import (
    HMAC_SECRET,
    create_operator_app,
    login_with_csrf,
    operator_settings,
)


def test_session_stub_roundtrip() -> None:
    org = uuid4()
    tok = issue_token_opts(
        TokenIssueOpts(
            secret=HMAC_SECRET,
            issuer="ibex-harness",
            audience="ibex-dashboard",
            org_id=org,
            permissions=7,
            subject="u",
            session_kind=SESSION_KIND_ACCESS,
            ttl_seconds=60,
        )
    )
    claims = verify_token_opts(
            tok,
            TokenVerifyOpts(
                secret=HMAC_SECRET,
                issuer="ibex-harness",
                audience="ibex-dashboard",
                expect_kind=SESSION_KIND_ACCESS,
            ),
        )
    assert claims.org_id == org
    csrf = mint_csrf_token(secret="c" * 32)
    assert verify_csrf_token(secret="c" * 32, cookie_value=csrf, header_value=csrf)
    assert not verify_csrf_token(secret="c" * 32, cookie_value=csrf, header_value="nope")


def test_session_stub_error_paths() -> None:
    with pytest.raises(SessionStubError):
        verify_token_opts(
            "a.b",
            TokenVerifyOpts(
                secret="s" * 32,
                issuer="i",
                audience="a",
                expect_kind="access",
            ),
        )
    with pytest.raises(SessionStubError):
        verify_token_opts(
            "a.b.c",
            TokenVerifyOpts(
                secret="s" * 32,
                issuer="i",
                audience="a",
                expect_kind="access",
            ),
        )
    org = uuid4()
    tok = issue_token_opts(
        TokenIssueOpts(
            secret="s" * 32,
            issuer="ibex-harness",
            audience="ibex-dashboard",
            org_id=org,
            permissions=1,
            subject="u",
            session_kind=SESSION_KIND_ACCESS,
            ttl_seconds=60,
        )
    )
    with pytest.raises(SessionStubError):
        verify_token_opts(
            tok,
            TokenVerifyOpts(
                secret="o" * 32,
                issuer="ibex-harness",
                audience="ibex-dashboard",
                expect_kind="access",
            ),
        )
    with pytest.raises(SessionStubError):
        verify_token_opts(
            tok,
            TokenVerifyOpts(
                secret="s" * 32,
                issuer="wrong",
                audience="ibex-dashboard",
                expect_kind="access",
            ),
        )
    with pytest.raises(SessionStubError):
        verify_token_opts(
            tok,
            TokenVerifyOpts(
                secret="s" * 32,
                issuer="ibex-harness",
                audience="ibex-dashboard",
                expect_kind=SESSION_KIND_REFRESH,
            ),
        )
    expired = issue_token_opts(
        TokenIssueOpts(
            secret="s" * 32,
            issuer="ibex-harness",
            audience="ibex-dashboard",
            org_id=org,
            permissions=1,
            subject="u",
            session_kind=SESSION_KIND_ACCESS,
            ttl_seconds=-10,
        )
    )
    with pytest.raises(SessionStubError):
        verify_token_opts(
            expired,
            TokenVerifyOpts(
                secret="s" * 32,
                issuer="ibex-harness",
                audience="ibex-dashboard",
                expect_kind=SESSION_KIND_ACCESS,
            ),
        )
    assert not verify_csrf_token(secret="c" * 32, cookie_value="noperiod", header_value="noperiod")


def test_operator_me_with_cookie_session(app_client) -> None:
    _, client = app_client
    login_with_csrf(client)
    me = client.get("/v1/operator/session/me")
    assert me.status_code == 200
    assert me.json()["auth"] == "cookie"
    assert me.json()["provisional"] is True


def test_session_refresh_rotates_csrf(app_client) -> None:
    _, client = app_client
    csrf = login_with_csrf(client)
    refresh = client.post(
        "/v1/operator/session/refresh",
        headers={"X-CSRF-Token": csrf},
    )
    assert refresh.status_code == 200
    assert refresh.json()["provisional"] is True
    assert "csrf_token" in refresh.json()
    new_csrf = refresh.json()["csrf_token"]
    logout = client.post(
        "/v1/operator/session/logout",
        headers={"X-CSRF-Token": new_csrf},
    )
    assert logout.status_code == 200
    me = client.get("/v1/operator/session/me")
    assert me.status_code == 401


def test_login_rejects_bad_pat(app_client) -> None:
    _, client = app_client
    resp = client.post("/v1/operator/session/login", json={"pat": "ibex_pat_wrong"})
    assert resp.status_code == 401


def test_login_requires_hmac_secret() -> None:
    settings = Settings(
        database_url="postgresql+asyncpg://ibex:ibex@127.0.0.1:5432/ibex",
        allowed_origins="http://localhost:3100",
        jwt_hmac_secret=None,
        dashboard_csrf_secret="c" * 32,
        operator_feature_enabled=True,
    )
    validator = StaticTokenValidator(
        {"ibex_pat_test_secret": ValidateResult(org_id=uuid4(), permissions=1)}
    )
    with create_operator_app(settings=settings, validator=validator) as (_, client):
        resp = client.post("/v1/operator/session/login", json={"pat": "ibex_pat_test_secret"})
        assert resp.status_code == 503


def test_refresh_missing_cookie(app_client) -> None:
    _, client = app_client
    resp = client.post("/v1/operator/session/refresh")
    assert resp.status_code == 401


def test_me_bearer_fallback(app_client) -> None:
    _, client = app_client
    resp = client.get(
        "/v1/operator/session/me",
        headers={"Authorization": "Bearer ibex_pat_test_secret"},
    )
    assert resp.status_code == 200
    assert resp.json()["auth"] == "bearer"


def test_me_bearer_auth_failed(app_client) -> None:
    _, client = app_client
    resp = client.get(
        "/v1/operator/session/me",
        headers={"Authorization": "Bearer bad"},
    )
    assert resp.status_code == 401


def test_operator_feature_kill_switch() -> None:
    settings = operator_settings(operator_feature_enabled=False)
    with create_operator_app(settings=settings) as (_, client):
        resp = client.post("/v1/operator/session/login", json={"pat": "ibex_pat_test_secret"})
        assert resp.status_code == 503


def test_login_auth_unavailable_maps_503(app_client) -> None:
    from app.auth.errors import AuthUnavailableError

    _, client = app_client
    with patch.object(
        client.app.state.api.validator,
        "validate",
        AsyncMock(side_effect=AuthUnavailableError("down")),
    ):
        resp = client.post("/v1/operator/session/login", json={"pat": "ibex_pat_test_secret"})
    assert resp.status_code == 503
    assert resp.json()["error"]["code"] == "SERVICE_DEGRADED"


def test_refresh_rejects_tampered_cookie(app_client) -> None:
    _, client = app_client
    csrf = login_with_csrf(client)
    client.cookies.set("ibex_refresh", "a.b.c")
    resp = client.post(
        "/v1/operator/session/refresh",
        headers={"X-CSRF-Token": csrf},
    )
    assert resp.status_code == 401


def test_me_rejects_tampered_access_cookie(app_client) -> None:
    _, client = app_client
    login_with_csrf(client)
    client.cookies.set("ibex_session", "a.b.c")
    resp = client.get("/v1/operator/session/me")
    assert resp.status_code == 401


def test_me_bearer_auth_unavailable(app_client) -> None:
    from app.auth.errors import AuthUnavailableError

    _, client = app_client
    with patch.object(
        client.app.state.api.validator,
        "validate",
        AsyncMock(side_effect=AuthUnavailableError("down")),
    ):
        resp = client.get(
            "/v1/operator/session/me",
            headers={"Authorization": "Bearer ibex_pat_test_secret"},
        )
    assert resp.status_code == 503


def test_me_bearer_validator_missing(app_client) -> None:
    _, client = app_client
    client.app.state.api.validator = None
    resp = client.get(
        "/v1/operator/session/me",
        headers={"Authorization": "Bearer ibex_pat_test_secret"},
    )
    assert resp.status_code == 503


def test_session_stub_bad_payload_and_legacy_kind() -> None:
    import base64
    import hashlib
    import hmac
    import json
    import time

    def _b64(data: bytes) -> str:
        return base64.urlsafe_b64encode(data).rstrip(b"=").decode("ascii")

    org = uuid4()
    header = _b64(json.dumps({"alg": "HS256", "typ": "JWT"}).encode())
    # Non-object JSON payload
    bad_payload = _b64(b"[1]")
    body = f"{header}.{bad_payload}"
    sig = _b64(hmac.new(HMAC_SECRET.encode(), body.encode(), hashlib.sha256).digest())
    with pytest.raises(SessionStubError, match="bad payload"):
        verify_token_opts(
            f"{body}.{sig}",
            TokenVerifyOpts(
                secret=HMAC_SECRET,
                issuer="ibex-harness",
                audience="ibex-dashboard",
                expect_kind=SESSION_KIND_ACCESS,
            ),
        )

    # Invalid JSON payload
    junk = _b64(b"{not-json")
    body2 = f"{header}.{junk}"
    sig2 = _b64(hmac.new(HMAC_SECRET.encode(), body2.encode(), hashlib.sha256).digest())
    with pytest.raises(SessionStubError, match="bad payload"):
        verify_token_opts(
            f"{body2}.{sig2}",
            TokenVerifyOpts(
                secret=HMAC_SECRET,
                issuer="ibex-harness",
                audience="ibex-dashboard",
                expect_kind=SESSION_KIND_ACCESS,
            ),
        )

    # Legacy token_kind claim still accepted
    now = int(time.time())
    payload = {
        "sub": "u",
        "org_id": str(org),
        "permissions": 1,
        "token_kind": SESSION_KIND_ACCESS,
        "iss": "ibex-harness",
        "aud": "ibex-dashboard",
        "iat": now,
        "exp": now + 60,
        "jti": "x",
    }
    payload_b64 = _b64(json.dumps(payload).encode())
    body3 = f"{header}.{payload_b64}"
    sig3 = _b64(hmac.new(HMAC_SECRET.encode(), body3.encode(), hashlib.sha256).digest())
    claims = verify_token_opts(
            f"{body3}.{sig3}",
            TokenVerifyOpts(
                secret=HMAC_SECRET,
                issuer="ibex-harness",
                audience="ibex-dashboard",
                expect_kind=SESSION_KIND_ACCESS,
            ),
        )
    assert claims.org_id == org
