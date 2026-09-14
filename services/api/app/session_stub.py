"""Provisional HS256 session JWT helpers for 4.P.0 (stdlib only; moves to auth in 4.P.1)."""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import secrets
import time
from dataclasses import dataclass
from typing import Any
from uuid import UUID

SESSION_KIND_ACCESS = "access"
SESSION_KIND_REFRESH = "refresh"


class SessionStubError(Exception):
    """Invalid or expired provisional session token."""


def _b64url(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode("ascii")


def _b64url_decode(data: str) -> bytes:
    pad = "=" * (-len(data) % 4)
    try:
        return base64.urlsafe_b64decode(data + pad)
    except ValueError as exc:
        # binascii.Error is a ValueError subclass.
        raise SessionStubError("bad encoding") from exc


@dataclass(frozen=True, slots=True)
class SessionClaims:
    sub: str
    org_id: UUID
    permissions: int
    session_kind: str  # SESSION_KIND_ACCESS | SESSION_KIND_REFRESH
    exp: int
    iat: int
    jti: str


@dataclass(frozen=True, slots=True)
class TokenIssueOpts:
    secret: str
    issuer: str
    audience: str
    org_id: UUID
    permissions: int
    subject: str
    session_kind: str
    ttl_seconds: int


@dataclass(frozen=True, slots=True)
class TokenVerifyOpts:
    secret: str
    issuer: str
    audience: str
    expect_kind: str


def issue_token_opts(opts: TokenIssueOpts) -> str:
    now = int(time.time())
    header = {"alg": "HS256", "typ": "JWT"}
    payload = {
        "iss": opts.issuer,
        "aud": opts.audience,
        "sub": opts.subject,
        "org_id": str(opts.org_id),
        "permissions": opts.permissions,
        "session_kind": opts.session_kind,
        "iat": now,
        "exp": now + opts.ttl_seconds,
        "jti": secrets.token_urlsafe(16),
        "provisional": True,  # 4.P.0 marker — remove when auth issues sessions
    }
    body = f"{_b64url(json.dumps(header, separators=(',', ':')).encode())}."
    body += _b64url(json.dumps(payload, separators=(',', ':')).encode())
    sig = hmac.new(opts.secret.encode("utf-8"), body.encode("ascii"), hashlib.sha256).digest()
    return f"{body}.{_b64url(sig)}"


def _split_jwt(token: str) -> tuple[str, str, str]:
    try:
        header_b64, payload_b64, sig_b64 = token.split(".")
    except ValueError as exc:
        raise SessionStubError("malformed token") from exc
    return header_b64, payload_b64, sig_b64


def _verify_signature(header_b64: str, payload_b64: str, sig_b64: str, *, secret: str) -> None:
    body = f"{header_b64}.{payload_b64}"
    expected = hmac.new(secret.encode("utf-8"), body.encode("ascii"), hashlib.sha256).digest()
    got_sig = _b64url_decode(sig_b64)
    if not hmac.compare_digest(expected, got_sig):
        raise SessionStubError("bad signature")


def _decode_payload(payload_b64: str) -> dict[str, Any]:
    try:
        payload = json.loads(_b64url_decode(payload_b64))
    except (json.JSONDecodeError, SessionStubError) as exc:
        raise SessionStubError("bad payload") from exc
    if not isinstance(payload, dict):
        raise SessionStubError("bad payload")
    return payload


def _session_kind_of(payload: dict[str, Any]) -> str | None:
    kind = payload.get("session_kind") or payload.get("token_kind")
    return None if kind is None else str(kind)


def _to_claims(payload: dict[str, Any]) -> SessionClaims:
    return SessionClaims(
        sub=str(payload.get("sub", "")),
        org_id=UUID(str(payload["org_id"])),
        permissions=int(payload.get("permissions", 0)),
        session_kind=str(_session_kind_of(payload)),
        exp=int(payload.get("exp", 0)),
        iat=int(payload.get("iat", 0)),
        jti=str(payload.get("jti", "")),
    )


def _validate_claims(payload: dict[str, Any], opts: TokenVerifyOpts) -> SessionClaims:
    if payload.get("iss") != opts.issuer or payload.get("aud") != opts.audience:
        raise SessionStubError("issuer/audience mismatch")
    if _session_kind_of(payload) != opts.expect_kind:
        raise SessionStubError("wrong token kind")
    if int(payload.get("exp", 0)) < int(time.time()):
        raise SessionStubError("expired")
    return _to_claims(payload)


def verify_token(
    token: str,
    *,
    secret: str,
    issuer: str,
    audience: str,
    expect_kind: str,
) -> SessionClaims:
    return verify_token_opts(
        token,
        TokenVerifyOpts(
            secret=secret,
            issuer=issuer,
            audience=audience,
            expect_kind=expect_kind,
        ),
    )


def verify_token_opts(token: str, opts: TokenVerifyOpts) -> SessionClaims:
    header_b64, payload_b64, sig_b64 = _split_jwt(token)
    _verify_signature(header_b64, payload_b64, sig_b64, secret=opts.secret)
    return _validate_claims(_decode_payload(payload_b64), opts)


def mint_csrf_token(*, secret: str) -> str:
    nonce = secrets.token_urlsafe(24)
    digest = hmac.new(secret.encode("utf-8"), nonce.encode("utf-8"), hashlib.sha256).hexdigest()
    return f"{nonce}.{digest}"


def verify_csrf_token(*, secret: str, cookie_value: str | None, header_value: str | None) -> bool:
    if not cookie_value or not header_value:
        return False
    if not hmac.compare_digest(cookie_value, header_value):
        return False
    try:
        nonce, digest = cookie_value.split(".", 1)
    except ValueError:
        return False
    expected = hmac.new(secret.encode("utf-8"), nonce.encode("utf-8"), hashlib.sha256).hexdigest()
    return hmac.compare_digest(expected, digest)
