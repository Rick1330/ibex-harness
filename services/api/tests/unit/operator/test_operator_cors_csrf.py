"""CORS and CSRF enforcement."""

from __future__ import annotations

from starlette.applications import Starlette

from app.middleware.cors import build_cors_middleware
from tests.unit.operator.conftest import create_operator_app, login_with_csrf, operator_settings


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
    login_with_csrf(client)
    resp = client.post("/v1/operator/events/publish-test", json={"hello": "world"})
    assert resp.status_code == 403
    assert resp.json()["error"]["code"] == "csrf_failed"


def test_csrf_rejects_mismatched_token(app_client) -> None:
    _, client = app_client
    login_with_csrf(client)
    resp = client.post(
        "/v1/operator/events/publish-test",
        json={"hello": "world"},
        headers={"X-CSRF-Token": "not-the-cookie-value"},
    )
    assert resp.status_code == 403
    assert resp.json()["error"]["code"] == "csrf_failed"


def test_csrf_accepts_matching_double_submit(app_client) -> None:
    _, client = app_client
    csrf = login_with_csrf(client)
    resp = client.post(
        "/v1/operator/events/publish-test",
        json={"hello": "world"},
        headers={"X-CSRF-Token": csrf},
    )
    assert resp.status_code == 200
    assert resp.json()["event_id"] >= 1


def test_csrf_misconfigured_without_secret() -> None:
    settings = operator_settings(dashboard_csrf_secret=None)
    with create_operator_app(settings=settings) as (_, client):
        login_with_csrf(client)
        resp = client.post("/v1/operator/events/publish-test", json={"x": 1})
        assert resp.status_code == 503
        assert resp.json()["error"]["code"] == "csrf_misconfigured"


def test_csrf_required_when_only_refresh_cookie(app_client) -> None:
    _, client = app_client
    login_with_csrf(client)
    # Drop access cookie; keep refresh — CSRF must still apply.
    client.cookies.pop("ibex_session", None)
    resp = client.post("/v1/operator/session/refresh")
    assert resp.status_code == 403
    assert resp.json()["error"]["code"] == "csrf_failed"


def test_build_cors_middleware_strips_star() -> None:
    mw = build_cors_middleware(Starlette(), allow_origins=["http://localhost:3100", "*"])
    assert "http://localhost:3100" in mw.allow_origins
    assert "*" not in mw.allow_origins
