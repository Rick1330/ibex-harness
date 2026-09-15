"""RS256-only operator session refresh (Auth-owned rotation)."""

from __future__ import annotations

import base64
import json
import time
from unittest.mock import AsyncMock, patch
from uuid import uuid4

from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import padding, rsa

from app.auth.client import StaticTokenValidator
from app.auth.errors import AuthFailedError, AuthUnavailableError
from app.auth.session_refresh import RefreshedSession, encode_issue_with_refresh
from app.session_stub import mint_csrf_token
from tests.unit.operator.conftest import CSRF_SECRET, create_operator_app, operator_settings

_RS256_PEM = "-----BEGIN PUBLIC KEY-----\nMIIBIjANBgkqhkiG9w0BAQEFAAOCAQ8AMIIBCgKCAQEA\n-----END PUBLIC KEY-----"


def _b64url(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode("ascii")


def _rs256_shaped_refresh() -> str:
    """JWT shape with alg=RS256 so refresh dispatches to Auth-owned path."""
    header = _b64url(json.dumps({"alg": "RS256", "typ": "JWT"}).encode())
    payload = _b64url(json.dumps({"session_kind": "refresh"}).encode())
    return f"{header}.{payload}.sig"


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
        client.cookies.set("ibex_refresh", _rs256_shaped_refresh())
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
        client.cookies.set("ibex_refresh", _rs256_shaped_refresh())
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
        client.cookies.set("ibex_refresh", _rs256_shaped_refresh())
        resp = client.post("/v1/operator/session/refresh", headers=_csrf_headers(client))
    assert resp.status_code == 503


def test_mixed_hmac_still_routes_rs256_cookie_to_auth() -> None:
    """HMAC configured must not mint HS256 access for an RS256 refresh cookie."""
    settings = _rs256_settings(jwt_hmac_secret="h" * 32)
    with (
        create_operator_app(settings=settings, validator=StaticTokenValidator({})) as (_, client),
        patch(
            "app.routers.session.refresh_operator_session",
            new=AsyncMock(
                return_value=RefreshedSession(access_token="a", refresh_token="r"),
            ),
        ) as refresh_fn,
    ):
        client.cookies.set("ibex_refresh", _rs256_shaped_refresh())
        resp = client.post("/v1/operator/session/refresh", headers=_csrf_headers(client))
    assert resp.status_code == 200
    assert resp.json()["provisional"] is False
    refresh_fn.assert_awaited_once()


def test_me_cookie_rs256_is_not_provisional() -> None:
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    pub_pem = (
        key.public_key()
        .public_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PublicFormat.SubjectPublicKeyInfo,
        )
        .decode("ascii")
    )
    org = str(uuid4())
    now = int(time.time())
    header = _b64url(json.dumps({"alg": "RS256", "typ": "JWT"}).encode())
    payload = _b64url(
        json.dumps(
            {
                "iss": "ibex-harness",
                "aud": "ibex-dashboard",
                "sub": "user-1",
                "org_id": org,
                "permissions": 1,
                "session_kind": "access",
                "iat": now,
                "exp": now + 60,
                "jti": "jti-me",
            }
        ).encode()
    )
    body = f"{header}.{payload}"
    sig = _b64url(key.sign(body.encode("ascii"), padding.PKCS1v15(), hashes.SHA256()))
    token = f"{body}.{sig}"
    settings = _rs256_settings(jwt_public_keys_pem=pub_pem)
    with create_operator_app(settings=settings, validator=StaticTokenValidator({})) as (_, client):
        client.cookies.set("ibex_session", token)
        resp = client.get("/v1/operator/session/me")
    assert resp.status_code == 200
    body_json = resp.json()
    assert body_json["provisional"] is False
    assert body_json["org_id"] == org


def test_refresh_non_hs256_alg_with_keys_routes_to_auth() -> None:
    """Missing/odd alg with public keys must not require HMAC (Auth-owned path)."""
    header = _b64url(json.dumps({"alg": "none", "typ": "JWT"}).encode())
    payload = _b64url(json.dumps({"session_kind": "refresh"}).encode())
    odd = f"{header}.{payload}.sig"
    with (
        create_operator_app(settings=_rs256_settings(), validator=StaticTokenValidator({})) as (
            _,
            client,
        ),
        patch(
            "app.routers.session.refresh_operator_session",
            new=AsyncMock(return_value=RefreshedSession(access_token="a", refresh_token="r")),
        ) as refresh_fn,
    ):
        client.cookies.set("ibex_refresh", odd)
        resp = client.post("/v1/operator/session/refresh", headers=_csrf_headers(client))
    assert resp.status_code == 200
    assert resp.json()["provisional"] is False
    refresh_fn.assert_awaited_once()
