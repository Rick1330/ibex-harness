"""CORS and CSRF enforcement."""

from __future__ import annotations

import pytest
from starlette.applications import Starlette

from app.middleware.cors import build_cors_middleware
from tests.unit.operator.conftest import create_operator_app, login_with_csrf, operator_settings

PUBLISH = "/v1/operator/events/publish-test"


def _assert_csrf_failed(resp) -> None:
    assert resp.status_code == 403
    assert resp.json()["error"]["code"] == "csrf_failed"


def _preflight(client, origin: str):
    return client.options(
        "/health",
        headers={"Origin": origin, "Access-Control-Request-Method": "GET"},
    )


def _publish(client, *, csrf: str | None = None, payload: dict | None = None):
    headers = {"X-CSRF-Token": csrf} if csrf is not None else {}
    return client.post(PUBLISH, json=payload or {"hello": "world"}, headers=headers)


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
    _assert_csrf_failed(_publish(client, csrf=csrf))


def test_csrf_accepts_matching_double_submit(app_client) -> None:
    _, client = app_client
    csrf = login_with_csrf(client)
    resp = _publish(client, csrf=csrf)
    assert resp.status_code == 200
    assert resp.json()["event_id"] >= 1


def test_csrf_misconfigured_without_secret() -> None:
    settings = operator_settings(dashboard_csrf_secret=None)
    with create_operator_app(settings=settings) as (_, client):
        login_with_csrf(client)
        resp = client.post(PUBLISH, json={"x": 1})
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
