"""RS256 dual-verify and CSRF edge coverage for session_stub."""

from __future__ import annotations

import base64
import json
from uuid import uuid4

import pytest
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import padding, rsa

from app.session_stub import (
    MAX_JWT_PART_LEN,
    MAX_SESSION_TOKEN_LEN,
    SESSION_KIND_ACCESS,
    SessionStubError,
    TokenVerifyOpts,
    _header_kid,
    _load_rsa_public_keys,
    mint_csrf_token,
    verify_csrf_token,
    verify_token_opts,
)


def _b64url(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode("ascii")


def _rsa_keypair() -> tuple[rsa.RSAPrivateKey, str]:
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    pub_pem = (
        key.public_key()
        .public_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PublicFormat.SubjectPublicKeyInfo,
        )
        .decode("ascii")
    )
    return key, pub_pem


def _sign_rs256(private_key: rsa.RSAPrivateKey, header: dict, payload: dict) -> str:
    header = {**header, "kid": header.get("kid", "v1")}
    hb = _b64url(json.dumps(header, separators=(",", ":")).encode())
    pb = _b64url(json.dumps(payload, separators=(",", ":")).encode())
    body = f"{hb}.{pb}"
    sig = private_key.sign(body.encode("ascii"), padding.PKCS1v15(), hashes.SHA256())
    return f"{body}.{_b64url(sig)}"


def _access_payload(org_id: str, *, exp_offset: int = 60) -> dict:
    import time

    now = int(time.time())
    return {
        "iss": "ibex-harness",
        "aud": "ibex-dashboard",
        "sub": "user-1",
        "org_id": org_id,
        "permissions": 1,
        "session_kind": SESSION_KIND_ACCESS,
        "iat": now,
        "exp": now + exp_offset,
        "jti": "jti-1",
        "sid": "sid-1",
    }


def test_verify_rs256_ok_and_multi_key_rotation() -> None:
    org = str(uuid4())
    key, pub = _rsa_keypair()
    _other, other_pub = _rsa_keypair()
    tok = _sign_rs256(key, {"alg": "RS256", "typ": "JWT"}, _access_payload(org))
    claims = verify_token_opts(
        tok,
        TokenVerifyOpts(
            secret=None,
            issuer="ibex-harness",
            audience="ibex-dashboard",
            expect_kind=SESSION_KIND_ACCESS,
            public_keys_pem=other_pub + "\n" + pub,
        ),
    )
    assert str(claims.org_id) == org
    assert claims.verify_method == "RS256"


def test_verify_rejects_malformed_nbf_claim() -> None:
    org = str(uuid4())
    key, pub = _rsa_keypair()
    payload = _access_payload(org)
    payload["nbf"] = "not-a-number"
    tok = _sign_rs256(key, {"alg": "RS256", "typ": "JWT"}, payload)
    opts = TokenVerifyOpts(
        secret=None,
        issuer="ibex-harness",
        audience="ibex-dashboard",
        expect_kind=SESSION_KIND_ACCESS,
        public_keys_pem=pub,
    )
    with pytest.raises(SessionStubError, match="invalid not-before claim"):
        verify_token_opts(tok, opts)


def test_verify_rejects_malformed_exp_claim() -> None:
    org = str(uuid4())
    key, pub = _rsa_keypair()
    payload = _access_payload(org)
    payload["exp"] = "not-a-number"
    tok = _sign_rs256(key, {"alg": "RS256", "typ": "JWT"}, payload)
    opts = TokenVerifyOpts(
        secret=None,
        issuer="ibex-harness",
        audience="ibex-dashboard",
        expect_kind=SESSION_KIND_ACCESS,
        public_keys_pem=pub,
    )
    with pytest.raises(SessionStubError, match="invalid expiration claim"):
        verify_token_opts(tok, opts)


@pytest.mark.parametrize(
    ("empty_pem", "match"),
    [
        (False, "bad signature|no public keys"),
        (True, "no public keys|no verify material"),
    ],
)
def test_verify_rs256_rejects_bad_material(empty_pem: bool, match: str) -> None:
    org = str(uuid4())
    key, _ = _rsa_keypair()
    tok = _sign_rs256(key, {"alg": "RS256", "typ": "JWT"}, _access_payload(org))
    pub = "" if empty_pem else _rsa_keypair()[1]
    opts = TokenVerifyOpts(
        secret=None,
        issuer="ibex-harness",
        audience="ibex-dashboard",
        expect_kind=SESSION_KIND_ACCESS,
        public_keys_pem=pub,
    )
    with pytest.raises(SessionStubError, match=match):
        verify_token_opts(tok, opts)


def test_verify_rejects_non_object_header() -> None:
    hb = _b64url(b"[1,2,3]")
    pb = _b64url(b"{}")
    token = f"{hb}.{pb}.sig"
    opts = TokenVerifyOpts(secret="s" * 32, issuer="i", audience="a", expect_kind="access")
    with pytest.raises(SessionStubError, match="bad header"):
        verify_token_opts(token, opts)


def test_session_token_and_jwt_parts_have_bounded_size() -> None:
    oversized_token_opts = TokenVerifyOpts(
        secret="s" * 32, issuer="i", audience="a", expect_kind="access"
    )
    with pytest.raises(SessionStubError, match="token too large"):
        verify_token_opts("x" * (MAX_SESSION_TOKEN_LEN + 1), oversized_token_opts)
    oversized_part = "x" * (MAX_JWT_PART_LEN + 1)
    oversized_part_opts = TokenVerifyOpts(
        secret="s" * 32, issuer="i", audience="a", expect_kind="access"
    )
    with pytest.raises(SessionStubError, match="token too large"):
        verify_token_opts(f"{oversized_part}.payload.signature", oversized_part_opts)


def test_rsa_loader_rejects_non_rsa_public_key() -> None:
    from cryptography.hazmat.primitives.asymmetric import ec

    key = ec.generate_private_key(ec.SECP256R1())
    pem = (
        key.public_key()
        .public_bytes(serialization.Encoding.PEM, serialization.PublicFormat.SubjectPublicKeyInfo)
        .decode("ascii")
    )
    with pytest.raises(SessionStubError, match="bad public key"):
        _load_rsa_public_keys(pem)


def test_rsa_loader_stops_on_malformed_trailing_pem() -> None:
    _, pem = _rsa_keypair()
    assert len(_load_rsa_public_keys(pem + "-----BEGIN PUBLIC KEY-----\nmalformed")) == 1


def test_header_kid_rejects_malformed_and_non_object_headers() -> None:
    malformed = _b64url(b"not-json")
    with pytest.raises(SessionStubError, match="bad header"):
        _header_kid(malformed)
    non_object = _b64url(b"[]")
    with pytest.raises(SessionStubError, match="bad header"):
        _header_kid(non_object)


def test_verify_rejects_missing_material() -> None:
    ok_h = _b64url(json.dumps({"alg": "HS256"}).encode())
    ok_p = _b64url(json.dumps({"iss": "i"}).encode())
    token = f"{ok_h}.{ok_p}.{_b64url(b'x')}"
    opts = TokenVerifyOpts(
        secret=None,
        issuer="i",
        audience="a",
        expect_kind="access",
        public_keys_pem=None,
    )
    with pytest.raises(SessionStubError, match="no verify material"):
        verify_token_opts(token, opts)


def test_csrf_missing_cookie_or_header_false() -> None:
    csrf = mint_csrf_token(secret="c" * 32)
    assert not verify_csrf_token(secret="c" * 32, cookie_value=None, header_value=csrf)
    assert not verify_csrf_token(secret="c" * 32, cookie_value=csrf, header_value=None)


def test_verify_rejects_alg_none_even_with_rs256_keys() -> None:
    """Protected-header alg must match verifier; alg=none is rejected."""
    org = str(uuid4())
    key, pub = _rsa_keypair()
    tok = _sign_rs256(key, {"alg": "none", "typ": "JWT"}, _access_payload(org))
    opts = TokenVerifyOpts(
        secret=None,
        issuer="ibex-harness",
        audience="ibex-dashboard",
        expect_kind=SESSION_KIND_ACCESS,
        public_keys_pem=pub,
    )
    with pytest.raises(SessionStubError, match="alg mismatch"):
        verify_token_opts(tok, opts)


def test_verify_rejects_alg_none_hs256_fallback() -> None:
    """alg=none must not fall through to HS256 even with a valid HMAC signature."""
    import hashlib
    import hmac
    import time

    org = str(uuid4())
    now = int(time.time())
    header = _b64url(json.dumps({"alg": "none"}).encode())
    payload = _b64url(
        json.dumps(
            {
                "iss": "ibex-harness",
                "aud": "ibex-dashboard",
                "sub": "u1",
                "org_id": org,
                "permissions": 1,
                "session_kind": SESSION_KIND_ACCESS,
                "iat": now,
                "exp": now + 60,
                "jti": "j",
            }
        ).encode()
    )
    body = f"{header}.{payload}"
    secret = "s" * 32
    sig = _b64url(hmac.new(secret.encode(), body.encode("ascii"), hashlib.sha256).digest())
    _, wrong_pub = _rsa_keypair()
    opts = TokenVerifyOpts(
        secret=secret,
        issuer="ibex-harness",
        audience="ibex-dashboard",
        expect_kind=SESSION_KIND_ACCESS,
        public_keys_pem=wrong_pub,
    )
    with pytest.raises(SessionStubError, match="alg mismatch"):
        verify_token_opts(f"{body}.{sig}", opts)


def test_verify_accepts_token_kind_alias() -> None:
    org = str(uuid4())
    key, pub = _rsa_keypair()
    payload = _access_payload(org)
    del payload["session_kind"]
    payload["token_kind"] = SESSION_KIND_ACCESS
    tok = _sign_rs256(key, {"alg": "RS256", "typ": "JWT"}, payload)
    claims = verify_token_opts(
        tok,
        TokenVerifyOpts(
            secret=None,
            issuer="ibex-harness",
            audience="ibex-dashboard",
            expect_kind=SESSION_KIND_ACCESS,
            public_keys_pem=pub,
        ),
    )
    assert claims.session_kind == SESSION_KIND_ACCESS


def test_verify_rejects_non_object_payload() -> None:
    hb = _b64url(json.dumps({"alg": "HS256"}).encode())
    pb = _b64url(b"[1,2,3]")
    token = f"{hb}.{pb}.{_b64url(b'x')}"
    opts = TokenVerifyOpts(secret="s" * 32, issuer="i", audience="a", expect_kind="access")
    with pytest.raises(SessionStubError, match="bad payload"):
        verify_token_opts(token, opts)


def test_csrf_mismatch_and_malformed_false() -> None:
    csrf = mint_csrf_token(secret="c" * 32)
    assert not verify_csrf_token(secret="c" * 32, cookie_value=csrf, header_value="other")
    assert not verify_csrf_token(secret="c" * 32, cookie_value="nosplit", header_value="nosplit")


def test_load_rsa_keys_rejects_private_pem() -> None:
    key, _ = _rsa_keypair()
    priv_pem = key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.NoEncryption(),
    ).decode("ascii")
    org = str(uuid4())
    tok = _sign_rs256(key, {"alg": "RS256", "typ": "JWT"}, _access_payload(org))
    opts = TokenVerifyOpts(
        secret=None,
        issuer="ibex-harness",
        audience="ibex-dashboard",
        expect_kind=SESSION_KIND_ACCESS,
        public_keys_pem=priv_pem,
    )
    with pytest.raises(SessionStubError, match="bad public key|no public keys|bad signature"):
        verify_token_opts(tok, opts)


@pytest.mark.parametrize(
    ("claim", "message"),
    [
        ("sub", "missing required claims"),
        ("org_id", "missing required claims"),
        ("exp", "expired"),
        ("iat", "missing required claims"),
        ("jti", "missing required claims"),
    ],
)
def test_verify_rs256_rejects_each_missing_required_claim(claim: str, message: str) -> None:
    key, pub = _rsa_keypair()
    payload = _access_payload(str(uuid4()))
    payload.pop(claim)
    token = _sign_rs256(key, {"alg": "RS256", "typ": "JWT"}, payload)
    opts = TokenVerifyOpts(
        secret=None,
        issuer="ibex-harness",
        audience="ibex-dashboard",
        expect_kind=SESSION_KIND_ACCESS,
        public_keys_pem=pub,
    )
    with pytest.raises(SessionStubError, match=message):
        verify_token_opts(token, opts)



def _rs256_verify_opts(pub: str) -> TokenVerifyOpts:
    return TokenVerifyOpts(
        secret=None,
        issuer="ibex-harness",
        audience="ibex-dashboard",
        expect_kind=SESSION_KIND_ACCESS,
        public_keys_pem=pub,
    )


def _assert_rs256_verify_rejects(token: str, pub: str, match: str) -> None:
    opts = _rs256_verify_opts(pub)
    with pytest.raises(SessionStubError, match=match):
        verify_token_opts(token, opts)


def test_verify_rejects_future_not_before() -> None:
    import time

    key, pub = _rsa_keypair()
    future = _access_payload(str(uuid4()))
    future["nbf"] = int(time.time()) + 60
    token = _sign_rs256(key, {"alg": "RS256", "typ": "JWT"}, future)
    _assert_rs256_verify_rejects(token, pub, "not yet valid")


def test_verify_rejects_missing_or_wrong_rs256_key_id() -> None:
    key, pub = _rsa_keypair()
    payload = _access_payload(str(uuid4()))
    missing = _sign_rs256(key, {"alg": "RS256", "typ": "JWT", "kid": ""}, payload)
    _assert_rs256_verify_rejects(missing, pub, "key id")
    wrong = _sign_rs256(key, {"alg": "RS256", "typ": "JWT", "kid": "old"}, payload)
    _assert_rs256_verify_rejects(wrong, pub, "key id")


def test_verify_rejects_missing_rs256_session_id() -> None:
    key, pub = _rsa_keypair()
    missing_sid = _access_payload(str(uuid4()))
    missing_sid.pop("sid")
    token = _sign_rs256(key, {"alg": "RS256", "typ": "JWT"}, missing_sid)
    _assert_rs256_verify_rejects(token, pub, "missing session claim")


def test_verify_rejects_wrong_jwt_type() -> None:
    key, pub = _rsa_keypair()
    token = _sign_rs256(key, {"alg": "RS256", "typ": "not-jwt"}, _access_payload(str(uuid4())))
    _assert_rs256_verify_rejects(token, pub, "typ mismatch")


def test_hs256_verifier_rejects_non_jwt_typ() -> None:
    import hashlib
    import hmac

    secret = "s" * 32
    header = _b64url(json.dumps({"alg": "HS256", "typ": "not-jwt"}).encode())
    payload = _b64url(json.dumps({"iss": "ibex-harness"}).encode())
    body = f"{header}.{payload}"
    signature = _b64url(hmac.new(secret.encode(), body.encode("ascii"), hashlib.sha256).digest())
    opts = TokenVerifyOpts(
        secret=secret,
        issuer="ibex-harness",
        audience="ibex-dashboard",
        expect_kind=SESSION_KIND_ACCESS,
    )
    with pytest.raises(SessionStubError, match="typ mismatch"):
        verify_token_opts(f"{body}.{signature}", opts)


def test_private_header_type_reader_rejects_invalid_and_non_object_json() -> None:
    from app.session_stub import _header_typ

    with pytest.raises(SessionStubError, match="bad header"):
        _header_typ("not-base64!")
    non_object = _b64url(b"[]")
    with pytest.raises(SessionStubError, match="bad header"):
        _header_typ(non_object)
