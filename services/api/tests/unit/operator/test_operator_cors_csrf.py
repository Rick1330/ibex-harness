"""CORS and CSRF enforcement."""

from __future__ import annotations

import pytest
from starlette.applications import Starlette

from app.middleware.cors import build_cors_middleware
from tests.unit.operator.conftest import create_operator_app, login_with_csrf, operator_settings

# Cookie-authenticated mutating route used to exercise CSRF (publish-test removed).
MUTATION = "/v1/operator/session/logout"


def _assert_csrf_failed(resp) -> None:
    assert resp.status_code == 403
    assert resp.json()["error"]["code"] == "csrf_failed"


def _preflight(client, origin: str):
    return client.options(
        "/health",
        headers={"Origin": origin, "Access-Control-Request-Method": "GET"},
    )


def _mutate(client, *, csrf: str | None = None):
    headers = {"X-CSRF-Token": csrf} if csrf is not None else {}
    return client.post(MUTATION, headers=headers)


def test_cors_allows_listed_origin(app_client) -> None:
    _, client = app_client
    resp = _preflight(client, "http://localhost:3100")
    assert resp.status_code == 200
    assert resp.headers.get("access-control-allow-origin") == "http://localhost:3100"
    assert resp.headers.get("access-control-allow-credentials") == "true"


def test_cors_rejects_disallowed_origin(app_client) -> None:
    _, client = app_client
    allowed = _preflight(client, "https://evil.example").headers.get("access-control-allow-origin")
    assert allowed != "https://evil.example"
    assert allowed in (None, "null", "")


@pytest.mark.parametrize(
    "csrf",
    [None, "not-the-cookie-value"],
    ids=["missing", "mismatch"],
)
def test_csrf_rejects_bad_token(app_client, csrf: str | None) -> None:
    _, client = app_client
    login_with_csrf(client)
    _assert_csrf_failed(_mutate(client, csrf=csrf))


def test_csrf_accepts_matching_double_submit(app_client) -> None:
    _, client = app_client
    csrf = login_with_csrf(client)
    resp = _mutate(client, csrf=csrf)
    assert resp.status_code == 200
    assert resp.json()["status"] == "ok"


def test_csrf_misconfigured_without_secret() -> None:
    settings = operator_settings(dashboard_csrf_secret=None)
    with create_operator_app(settings=settings) as (_, client):
        login_with_csrf(client)
        resp = client.post(MUTATION)
        assert resp.status_code == 503
        assert resp.json()["error"]["code"] == "csrf_misconfigured"


def test_csrf_required_when_only_refresh_cookie(app_client) -> None:
    _, client = app_client
    login_with_csrf(client)
    client.cookies.pop("ibex_session", None)
    _assert_csrf_failed(client.post("/v1/operator/session/refresh"))


def test_build_cors_middleware_strips_star() -> None:
    mw = build_cors_middleware(Starlette(), allow_origins=["http://localhost:3100", "*"])
    assert "http://localhost:3100" in mw.allow_origins
    assert "*" not in mw.allow_origins


@pytest.mark.parametrize(
    ("origin", "referer", "expected_status", "expected_code"),
    [
        (None, "https://operator.ibexharness.com/settings", 401, None),
        (None, "https://evil.example/settings", 403, "origin_failed"),
        (None, None, 403, "origin_failed"),
        ("https://evil.example", "https://operator.ibexharness.com/", 403, "origin_failed"),
    ],
)
def test_production_csrf_origin_and_referer_policy(
    origin: str | None,
    referer: str | None,
    expected_status: int,
    expected_code: str | None,
) -> None:
    from app.session_stub import mint_csrf_token
    from tests.unit.operator.conftest import CSRF_SECRET

    settings = operator_settings(
        environment="staging",
        jwt_hmac_secret=None,
        jwt_public_keys_pem="configured-public-key",
        redis_url="redis://127.0.0.1:6379/0",
        cookie_secure=True,
    )
    csrf = mint_csrf_token(secret=CSRF_SECRET)
    headers = {
        "Cookie": f"ibex_session=opaque; ibex_csrf={csrf}",
        "X-CSRF-Token": csrf,
    }
    if origin is not None:
        headers["Origin"] = origin
    if referer is not None:
        headers["Referer"] = referer
    with create_operator_app(settings=settings) as (_, client):
        response = client.post(MUTATION, headers=headers)
    assert response.status_code == expected_status
    if expected_code:
        assert response.json()["error"]["code"] == expected_code
