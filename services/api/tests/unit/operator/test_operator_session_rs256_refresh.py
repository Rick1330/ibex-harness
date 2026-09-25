"""RS256-only operator session refresh (Auth-owned rotation)."""

from __future__ import annotations

import base64
import json
import time
from unittest.mock import AsyncMock, patch
from uuid import uuid4

import pytest
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


def _logout_settings(public_key: str):
    return _rs256_settings(
        jwt_public_keys_pem=public_key,
        environment="staging",
        operator_feature_enabled=True,
        redis_url="redis://127.0.0.1:6379/0",
        cookie_secure=True,
    )


def _signed_session_token(
    key,
    *,
    kind: str,
    session_id: str,
    family_id: str,
    jti: str,
    expires_in: int,
) -> str:
    now = int(time.time())
    header = _b64url(json.dumps({"alg": "RS256", "typ": "JWT", "kid": "v1"}).encode())
    payload = _b64url(
        json.dumps(
            {
                "iss": "ibex-harness",
                "aud": "ibex-dashboard",
                "sub": "user-1",
                "org_id": str(uuid4()),
                "permissions": 1,
                "session_kind": kind,
                "iat": now - 1,
                "exp": now + expires_in,
                "jti": jti,
                "sid": session_id,
                "fid": family_id,
            }
        ).encode()
    )
    body = f"{header}.{payload}"
    signature = _b64url(key.sign(body.encode("ascii"), padding.PKCS1v15(), hashes.SHA256()))
    return f"{body}.{signature}"


def _assert_session_cookies_deleted(response) -> None:
    headers = response.headers.get_list("set-cookie")
    for name in ("ibex_session", "ibex_refresh", "ibex_csrf"):
        value = next((header for header in headers if header.startswith(f"{name}=")), None)
        assert value is not None, f"missing deletion for {name}: {headers}"
        assert "Max-Age=0" in value
        assert "Path=/" in value
        assert "Secure" in value
        assert "SameSite=lax" in value
        if name != "ibex_csrf":
            assert "HttpOnly" in value
        else:
            assert "HttpOnly" not in value


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
    _assert_rs256_refresh_maps_error(AuthFailedError("bad"), 401)


def test_rs256_refresh_unavailable_maps_503() -> None:
    _assert_rs256_refresh_maps_error(AuthUnavailableError("down"), 503)


def _assert_rs256_refresh_maps_error(exc: Exception, status: int) -> None:
    with (
        create_operator_app(settings=_rs256_settings(), validator=StaticTokenValidator({})) as (
            _,
            client,
        ),
        patch(
            "app.routers.session.refresh_operator_session",
            new=AsyncMock(side_effect=exc),
        ),
    ):
        client.cookies.set("ibex_refresh", _rs256_shaped_refresh())
        resp = client.post("/v1/operator/session/refresh", headers=_csrf_headers(client))
    assert resp.status_code == status


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
    header = _b64url(json.dumps({"alg": "RS256", "typ": "JWT", "kid": "v1"}).encode())
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
                "sid": "sid-me",
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


def test_logout_uses_valid_refresh_when_access_is_expired_and_clears_all_cookies() -> None:
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    pub_pem = key.public_key().public_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PublicFormat.SubjectPublicKeyInfo,
    ).decode("ascii")
    access = _signed_session_token(
        key, kind="access", session_id="sid-expired", family_id="fid-expired", jti="jti-expired", expires_in=-1
    )
    refresh = _signed_session_token(
        key, kind="refresh", session_id="sid-expired", family_id="fid-expired", jti="rjti-valid", expires_in=3600
    )
    with (
        create_operator_app(settings=_logout_settings(pub_pem), validator=StaticTokenValidator({})) as (
            _, client
        ),
        patch("app.routers.session.revoke_operator_session", new=AsyncMock()) as revoke,
    ):
        csrf = _csrf_headers(client)
        client.cookies.set("ibex_session", access)
        client.cookies.set("ibex_refresh", refresh)
        response = client.post(
            "/v1/operator/session/logout",
            headers={**csrf, "Origin": "https://operator.ibexharness.com"},
        )
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}
    revoke.assert_awaited_once()
    kwargs = revoke.await_args.kwargs
    assert kwargs["session_id"] == "sid-expired"
    assert kwargs["family_id"] == "fid-expired"
    assert kwargs["access_token"] == ""
    assert kwargs["access_jti"] == ""
    assert kwargs["refresh_token"] == refresh
    _assert_session_cookies_deleted(response)


def test_logout_refresh_only_survives_authservice_outage_as_degraded_but_clears_cookies() -> None:
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    pub_pem = key.public_key().public_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PublicFormat.SubjectPublicKeyInfo,
    ).decode("ascii")
    refresh = _signed_session_token(
        key, kind="refresh", session_id="sid-only", family_id="fid-only", jti="rjti-only", expires_in=3600
    )
    with (
        create_operator_app(settings=_logout_settings(pub_pem), validator=StaticTokenValidator({})) as (
            _, client
        ),
        patch(
            "app.routers.session.revoke_operator_session",
            new=AsyncMock(side_effect=AuthUnavailableError("down")),
        ),
    ):
        csrf = _csrf_headers(client)
        client.cookies.set("ibex_refresh", refresh)
        response = client.post(
            "/v1/operator/session/logout",
            headers={**csrf, "Origin": "https://operator.ibexharness.com"},
        )
    assert response.status_code == 503
    assert response.json()["error"]["code"] == "SERVICE_DEGRADED"
    _assert_session_cookies_deleted(response)


def test_logout_mismatched_valid_proofs_are_rejected_without_rpc_and_cleared() -> None:
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    pub_pem = key.public_key().public_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PublicFormat.SubjectPublicKeyInfo,
    ).decode("ascii")
    access = _signed_session_token(
        key, kind="access", session_id="sid-a", family_id="fid-a", jti="jti-a", expires_in=3600
    )
    refresh = _signed_session_token(
        key, kind="refresh", session_id="sid-b", family_id="fid-b", jti="jti-b", expires_in=3600
    )
    with (
        create_operator_app(settings=_logout_settings(pub_pem), validator=StaticTokenValidator({})) as (
            _, client
        ),
        patch("app.routers.session.revoke_operator_session", new=AsyncMock()) as revoke,
    ):
        csrf = _csrf_headers(client)
        client.cookies.set("ibex_session", access)
        client.cookies.set("ibex_refresh", refresh)
        response = client.post(
            "/v1/operator/session/logout",
            headers={**csrf, "Origin": "https://operator.ibexharness.com"},
        )
    assert response.status_code == 401
    revoke.assert_not_awaited()
    _assert_session_cookies_deleted(response)


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


@pytest.mark.parametrize(
    ("rpc_error", "expected_status"),
    [(None, 200), (AuthFailedError("bad"), 401), (AuthUnavailableError("down"), 503)],
)
def test_production_me_delegates_cookie_validation_to_authservice(
    rpc_error: Exception | None, expected_status: int
) -> None:
    from app.auth.session_refresh import ValidatedSession

    org = str(uuid4())
    validated = ValidatedSession(
        subject="user-1", org_id=org, permissions=0, session_id="sid-1", jti="jti-1"
    )
    error = rpc_error
    with (
        create_operator_app(
            settings=_logout_settings(_RS256_PEM),
            validator=StaticTokenValidator({}),
        ) as (_, client),
        patch(
            "app.routers.session.validate_operator_session",
            new=AsyncMock(side_effect=error) if error else AsyncMock(return_value=validated),
        ) as validate,
    ):
        client.cookies.set("ibex_session", "opaque-auth-owned-token")
        response = client.get("/v1/operator/session/me")
    assert response.status_code == expected_status
    validate.assert_awaited_once()
    assert validate.await_args.kwargs["access_token"] == "opaque-auth-owned-token"
    if expected_status == 200:
        assert response.json() == {
            "auth": "cookie",
            "org_id": org,
            "sub": "user-1",
            "provisional": False,
        }
    elif expected_status == 503:
        assert response.json()["error"]["code"] == "SERVICE_DEGRADED"


def test_production_logout_without_any_valid_proof_clears_all_cookies() -> None:
    with create_operator_app(
        settings=_logout_settings(_RS256_PEM),
        validator=StaticTokenValidator({}),
    ) as (_, client):
        response = client.post(
            "/v1/operator/session/logout",
            headers={**_csrf_headers(client), "Origin": "https://operator.ibexharness.com"},
        )
    assert response.status_code == 401
    assert response.json()["error"]["code"] == "INVALID_TOKEN"
    _assert_session_cookies_deleted(response)


def test_production_logout_authservice_rejection_clears_all_cookies() -> None:
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    pub_pem = key.public_key().public_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PublicFormat.SubjectPublicKeyInfo,
    ).decode("ascii")
    access = _signed_session_token(
        key, kind="access", session_id="sid-1", family_id="fid-1", jti="jti-1", expires_in=300
    )
    with (
        create_operator_app(
            settings=_logout_settings(pub_pem), validator=StaticTokenValidator({})
        ) as (_, client),
        patch(
            "app.routers.session.revoke_operator_session",
            new=AsyncMock(side_effect=AuthFailedError("rejected")),
        ) as revoke,
    ):
        client.cookies.set("ibex_session", access)
        response = client.post(
            "/v1/operator/session/logout",
            headers={**_csrf_headers(client), "Origin": "https://operator.ibexharness.com"},
        )
    assert response.status_code == 401
    assert response.json()["error"]["code"] == "INVALID_TOKEN"
    revoke.assert_awaited_once()
    _assert_session_cookies_deleted(response)


def test_production_login_uses_authservice_and_sets_opaque_session_cookies() -> None:
    from app.auth.session_refresh import RefreshedSession

    result = StaticTokenValidator(
        {"ibex_pat_test_secret": __import__("app.auth.client", fromlist=["ValidateResult"]).ValidateResult(
            org_id=uuid4(), permissions=1, user_id="user-1"
        )}
    )
    settings = _logout_settings(_RS256_PEM)
    with (
        create_operator_app(settings=settings, validator=result) as (_, client),
        patch(
            "app.routers.session.issue_operator_session",
            new=AsyncMock(
                return_value=RefreshedSession("opaque-access", "opaque-refresh")
            ),
        ) as issue,
    ):
        response = client.post(
            "/v1/operator/session/login", json={"pat": "ibex_pat_test_secret"}
        )
    assert response.status_code == 200
    assert response.json()["provisional"] is False
    assert issue.await_args.kwargs["pat"] == "ibex_pat_test_secret"
    cookies = response.headers.get_list("set-cookie")
    assert any(value.startswith("ibex_session=opaque-access") for value in cookies)
    assert any(value.startswith("ibex_refresh=opaque-refresh") for value in cookies)


def test_refresh_via_auth_omits_csrf_cookie_when_secret_is_absent() -> None:
    import asyncio

    from starlette.responses import Response

    from app.routers.session import _refresh_via_auth

    with patch(
        "app.routers.session.refresh_operator_session",
        new=AsyncMock(return_value=RefreshedSession("access", "refresh")),
    ):
        body = asyncio.run(
            _refresh_via_auth(
                response=Response(),
                settings=_rs256_settings(dashboard_csrf_secret=None),
                refresh_token="proof",
            )
        )
    assert body["csrf_token"] == ""


def test_refresh_via_auth_rejects_missing_public_keys_before_rpc() -> None:
    import asyncio

    from starlette.responses import Response

    from app.errors import ApiError
    from app.routers.session import _refresh_via_auth

    rpc = AsyncMock()
    with (
        patch("app.routers.session.refresh_operator_session", new=rpc),
        pytest.raises(ApiError) as exc,
    ):
        asyncio.run(
            _refresh_via_auth(
                response=Response(),
                settings=_rs256_settings(jwt_public_keys_pem=None),
                refresh_token="proof",
            )
        )
    assert exc.value.code == "SERVICE_DEGRADED"
    rpc.assert_not_awaited()


@pytest.mark.parametrize(
    ("error", "expected_status", "expected_code"),
    [
        (AuthFailedError("bad"), 401, "INVALID_TOKEN"),
        (AuthUnavailableError("down"), 503, "SERVICE_DEGRADED"),
    ],
)
def test_production_login_maps_authservice_issue_errors(
    error: Exception, expected_status: int, expected_code: str
) -> None:
    from app.auth.client import ValidateResult

    validator = StaticTokenValidator(
        {
            "ibex_pat_test_secret": ValidateResult(
                org_id=uuid4(), permissions=1, user_id="user-1"
            )
        }
    )
    with (
        create_operator_app(
            settings=_logout_settings(_RS256_PEM), validator=validator
        ) as (_, client),
        patch(
            "app.routers.session.issue_operator_session",
            new=AsyncMock(side_effect=error),
        ) as issue,
    ):
        response = client.post(
            "/v1/operator/session/login", json={"pat": "ibex_pat_test_secret"}
        )
    assert response.status_code == expected_status
    assert response.json()["error"]["code"] == expected_code
    issue.assert_awaited_once()


def test_provisional_hmac_issuer_is_rejected_outside_development() -> None:
    from app.errors import ApiError
    from app.routers.session import _require_hmac

    settings = _rs256_settings(
        environment="staging",
        redis_url="redis://127.0.0.1:6379/0",
        cookie_secure=True,
    )
    with pytest.raises(ApiError) as exc:
        _require_hmac(settings)
    assert exc.value.code == "SERVICE_DEGRADED"
