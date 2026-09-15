"""RS256-only operator session refresh (Auth-owned rotation)."""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

from app.auth.client import StaticTokenValidator
from app.auth.errors import AuthFailedError, AuthUnavailableError
from app.auth.session_refresh import RefreshedSession, encode_issue_with_refresh
from app.session_stub import mint_csrf_token
from tests.unit.operator.conftest import CSRF_SECRET, create_operator_app, operator_settings

_RS256_PEM = "-----BEGIN PUBLIC KEY-----\nMIIBIjANBgkqhkiG9w0BAQEFAAOCAQ8AMIIBCgKCAQEA\n-----END PUBLIC KEY-----"


def _rs256_settings(**kwargs: object):
    base = {
        "jwt_hmac_secret": None,
        "jwt_public_keys_pem": _RS256_PEM,
        "dashboard_csrf_secret": CSRF_SECRET,
    }
    base.update(kwargs)
    return operator_settings(**base)


def _csrf_headers(client) -> dict[str, str]:
    csrf = mint_csrf_token(secret=CSRF_SECRET)
    client.cookies.set("ibex_csrf", csrf)
    return {"X-CSRF-Token": csrf}


def test_encode_issue_with_refresh_roundtrips_field() -> None:
    payload = encode_issue_with_refresh("refresh-token-value")
    assert payload[0] == 0x0A
    assert b"refresh-token-value" in payload


def test_rs256_refresh_success_sets_cookies() -> None:
    with (
        create_operator_app(settings=_rs256_settings(), validator=StaticTokenValidator({})) as (
            _,
            client,
        ),
        patch(
            "app.routers.session.refresh_operator_session",
            new=AsyncMock(
                return_value=RefreshedSession(
                    access_token="access-rs256",
                    refresh_token="refresh-rs256",
                )
            ),
        ) as refresh_fn,
    ):
        client.cookies.set("ibex_refresh", "old-refresh")
        resp = client.post("/v1/operator/session/refresh", headers=_csrf_headers(client))
    assert resp.status_code == 200
    body = resp.json()
    assert body["provisional"] is False
    assert body["csrf_token"]
    assert body["status"] == "ok"
    refresh_fn.assert_awaited_once()


def test_rs256_refresh_auth_failed_maps_401() -> None:
    with (
        create_operator_app(settings=_rs256_settings(), validator=StaticTokenValidator({})) as (
            _,
            client,
        ),
        patch(
            "app.routers.session.refresh_operator_session",
            new=AsyncMock(side_effect=AuthFailedError("bad")),
        ),
    ):
        client.cookies.set("ibex_refresh", "bad-refresh")
        resp = client.post("/v1/operator/session/refresh", headers=_csrf_headers(client))
    assert resp.status_code == 401


def test_rs256_refresh_unavailable_maps_503() -> None:
    with (
        create_operator_app(settings=_rs256_settings(), validator=StaticTokenValidator({})) as (
            _,
            client,
        ),
        patch(
            "app.routers.session.refresh_operator_session",
            new=AsyncMock(side_effect=AuthUnavailableError("down")),
        ),
    ):
        client.cookies.set("ibex_refresh", "old-refresh")
        resp = client.post("/v1/operator/session/refresh", headers=_csrf_headers(client))
    assert resp.status_code == 503
