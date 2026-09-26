"""Provisional session JWT helpers (4.P.0 HS256 + 4.P.1 RS256 dual-verify)."""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import logging
import secrets
import time
from dataclasses import dataclass
from typing import Any
from uuid import UUID

from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import padding
from cryptography.hazmat.primitives.asymmetric.rsa import RSAPublicKey

SESSION_KIND_ACCESS = "access"
SESSION_KIND_REFRESH = "refresh"
SESSION_KIND_STEP_UP = "step_up"
_BAD_HEADER = "bad header"

# Bound externally supplied cookies/headers before JWT parse (DoS / memory).
MAX_SESSION_TOKEN_LEN = 8192
MAX_JWT_PART_LEN = 4096

_LOG = logging.getLogger(__name__)


class SessionStubError(Exception):
    """Invalid or expired provisional session token."""


def _b64url(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode("ascii")


def _b64url_decode(data: str) -> bytes:
    pad = "=" * (-len(data) % 4)
    try:
        return base64.urlsafe_b64decode(data + pad)
    except ValueError as exc:
        raise SessionStubError("bad encoding") from exc


@dataclass(frozen=True, slots=True)
class SessionClaims:
    sub: str
    org_id: UUID
    permissions: int
    session_kind: str  # SESSION_KIND_ACCESS | SESSION_KIND_REFRESH | SESSION_KIND_STEP_UP
    exp: int
    iat: int
    jti: str
    # Verifier outcome (not the unverified JWT header alg).
    verify_method: str  # "RS256" | "HS256"
    session_id: str = ""
    family_id: str | None = None
    action: str | None = None


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
    session_id: str | None = None
    family_id: str | None = None
    action: str | None = None


@dataclass(frozen=True, slots=True)
class TokenVerifyOpts:
    secret: str | None
    issuer: str
    audience: str
    expect_kind: str
    public_keys_pem: str | None = None
    key_id: str = "v1"


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
        "nbf": now,
        "exp": now + opts.ttl_seconds,
        "jti": secrets.token_urlsafe(16),
        "sid": opts.session_id or secrets.token_urlsafe(16),
        "provisional": True,  # 4.P.0 marker — remove when auth issues sessions
    }
    if opts.family_id:
        payload["fid"] = opts.family_id
    if opts.action:
        payload["action"] = opts.action
    body = f"{_b64url(json.dumps(header, separators=(',', ':')).encode())}."
    body += _b64url(json.dumps(payload, separators=(",", ":")).encode())
    sig = hmac.new(opts.secret.encode("utf-8"), body.encode("ascii"), hashlib.sha256).digest()
    return f"{body}.{_b64url(sig)}"


@dataclass(frozen=True, slots=True)
class _JWTParts:
    header_b64: str
    payload_b64: str
    sig_b64: str


def _reject_oversized_token(token: str) -> None:
    if len(token) > MAX_SESSION_TOKEN_LEN:
        raise SessionStubError("token too large")


def _reject_oversized_parts(*parts: str) -> None:
    if any(len(part) > MAX_JWT_PART_LEN for part in parts):
        raise SessionStubError("token too large")


def _split_jwt(token: str) -> _JWTParts:
    _reject_oversized_token(token)
    try:
        header_b64, payload_b64, sig_b64 = token.split(".")
    except ValueError as exc:
        raise SessionStubError("malformed token") from exc
    _reject_oversized_parts(header_b64, payload_b64, sig_b64)
    return _JWTParts(header_b64=header_b64, payload_b64=payload_b64, sig_b64=sig_b64)


def _verify_hs256(parts: _JWTParts, *, secret: str) -> None:
    body = f"{parts.header_b64}.{parts.payload_b64}"
    expected = hmac.new(secret.encode("utf-8"), body.encode("ascii"), hashlib.sha256).digest()
    got_sig = _b64url_decode(parts.sig_b64)
    if not hmac.compare_digest(expected, got_sig):
        raise SessionStubError("bad signature")


def _load_rsa_public_keys(pem_blob: str) -> list[RSAPublicKey]:
    keys: list[RSAPublicKey] = []
    rest = pem_blob.encode("utf-8")
    while b"-----BEGIN" in rest:
        try:
            key = serialization.load_pem_public_key(rest)
        except ValueError:
            break
        if not isinstance(key, RSAPublicKey):
            raise SessionStubError("bad public key")
        keys.append(key)
        # Advance past this PEM block for multi-key blobs.
        end = rest.find(b"-----END")
        if end < 0:
            break
        nl = rest.find(b"\n", end)
        rest = rest[nl + 1 :] if nl >= 0 else b""
    return keys


def _verify_rs256(parts: _JWTParts, *, public_keys_pem: str) -> None:
    keys = _load_rsa_public_keys(public_keys_pem)
    if not keys:
        raise SessionStubError("no public keys")
    body = f"{parts.header_b64}.{parts.payload_b64}".encode("ascii")
    sig = _b64url_decode(parts.sig_b64)
    last: Exception | None = None
    for key in keys:
        try:
            key.verify(sig, body, padding.PKCS1v15(), hashes.SHA256())
            return
        except Exception as exc:  # noqa: BLE001 — try next key
            last = exc
            continue
    raise SessionStubError("bad signature") from last


def _header_alg(header_b64: str) -> str:
    try:
        header = json.loads(_b64url_decode(header_b64))
    except (json.JSONDecodeError, SessionStubError) as exc:
        raise SessionStubError(_BAD_HEADER) from exc
    if not isinstance(header, dict):
        raise SessionStubError(_BAD_HEADER)
    return str(header.get("alg", ""))


def _header_typ(header_b64: str) -> str:
    try:
        header = json.loads(_b64url_decode(header_b64))
    except (json.JSONDecodeError, SessionStubError) as exc:
        raise SessionStubError(_BAD_HEADER) from exc
    if not isinstance(header, dict):
        raise SessionStubError(_BAD_HEADER)
    return str(header.get("typ", ""))


def _header_kid(header_b64: str) -> str:
    try:
        header = json.loads(_b64url_decode(header_b64))
    except (json.JSONDecodeError, SessionStubError) as exc:
        raise SessionStubError(_BAD_HEADER) from exc
    if not isinstance(header, dict):
        raise SessionStubError(_BAD_HEADER)
    kid = header.get("kid")
    if not isinstance(kid, str) or not kid.strip():
        raise SessionStubError("key id missing")
    return kid.strip()


def peek_token_alg(token: str) -> str:
    """Return the JWT alg claim without verifying the signature."""
    return _header_alg(_split_jwt(token).header_b64)


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


def _to_claims(payload: dict[str, Any], *, verify_method: str) -> SessionClaims:
    try:
        return SessionClaims(
            sub=str(payload["sub"]),
            org_id=UUID(str(payload["org_id"])),
            permissions=int(payload.get("permissions", 0)),
            session_kind=str(_session_kind_of(payload)),
            exp=int(payload["exp"]),
            iat=int(payload["iat"]),
            jti=str(payload["jti"]),
            session_id=str(payload.get("sid", "")),
            family_id=_optional_str(payload, "fid"),
            action=_optional_str(payload, "action"),
            verify_method=verify_method,
        )
    except (KeyError, TypeError, ValueError) as exc:
        raise SessionStubError("missing required claims") from exc


def _optional_str(payload: dict[str, Any], key: str) -> str | None:
    if key not in payload or payload[key] is None:
        return None
    return str(payload[key])


def _validate_claims(
    payload: dict[str, Any], opts: TokenVerifyOpts, *, verify_method: str
) -> SessionClaims:
    _assert_issuer_audience(payload, opts)
    _assert_expected_kind(payload, opts.expect_kind)
    _assert_temporal_claims(payload)
    claims = _to_claims(payload, verify_method=verify_method)
    _assert_rs256_session_id(claims, verify_method)
    return claims


def _assert_expected_kind(payload: dict[str, Any], expect_kind: str) -> None:
    if _session_kind_of(payload) != expect_kind:
        raise SessionStubError("wrong token kind")


def _assert_rs256_session_id(claims: SessionClaims, verify_method: str) -> None:
    if verify_method == "RS256" and not claims.session_id:
        raise SessionStubError("missing session claim")


def _assert_issuer_audience(payload: dict[str, Any], opts: TokenVerifyOpts) -> None:
    if payload.get("iss") != opts.issuer or payload.get("aud") != opts.audience:
        raise SessionStubError("issuer/audience mismatch")


def _assert_temporal_claims(payload: dict[str, Any]) -> None:
    now = int(time.time())
    if int(payload.get("exp", 0)) < now:
        raise SessionStubError("expired")
    _assert_not_before(payload, now)


def _assert_not_before(payload: dict[str, Any], now: int) -> None:
    if "nbf" not in payload:
        return
    try:
        not_before = int(payload["nbf"])
    except (TypeError, ValueError) as exc:
        raise SessionStubError("invalid not-before claim") from exc
    if not_before > now:
        raise SessionStubError("not yet valid")


def verify_token_opts(token: str, opts: TokenVerifyOpts) -> SessionClaims:
    """Verify RS256 or HS256; protected-header alg must match the verifier used."""
    parts = _split_jwt(token)
    alg = _header_alg(parts.header_b64)
    payload = _decode_payload(parts.payload_b64)
    if alg == "RS256":
        return _verify_rs256_token(parts, payload, opts)
    if alg == "HS256":
        return _verify_hs256_token(parts, payload, opts)
    raise SessionStubError("alg mismatch")


def _verify_rs256_token(
    parts: _JWTParts,
    payload: dict[str, Any],
    opts: TokenVerifyOpts,
) -> SessionClaims:
    if not opts.public_keys_pem:
        raise SessionStubError("no verify material")
    if _header_typ(parts.header_b64) != "JWT":
        raise SessionStubError("typ mismatch")
    if _header_kid(parts.header_b64) != opts.key_id.strip():
        raise SessionStubError("key id mismatch")
    _verify_rs256(parts, public_keys_pem=opts.public_keys_pem)
    return _validate_claims(payload, opts, verify_method="RS256")


def _verify_hs256_token(
    parts: _JWTParts,
    payload: dict[str, Any],
    opts: TokenVerifyOpts,
) -> SessionClaims:
    if not opts.secret:
        raise SessionStubError("no verify material")
    if _header_typ(parts.header_b64) != "JWT":
        raise SessionStubError("typ mismatch")
    _verify_hs256(parts, secret=opts.secret)
    _LOG.warning(
        "provisional_hs256_verify=1 issuer=%s audience=%s",
        opts.issuer,
        opts.audience,
    )
    return _validate_claims(payload, opts, verify_method="HS256")


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
