"""Minimal S3-compatible helpers for org-deletion / capture archive (4.P.3).

AES-256-GCM envelope matches Go packages/crypto + objectstore.ArchivedBlob.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import logging
import os
import secrets
from datetime import UTC, datetime
from typing import Any
from urllib.parse import quote, urlparse

import httpx
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

logger = logging.getLogger(__name__)

_NONCE_SIZE = 12
_DEK_SIZE = 32
_DEFAULT_KEY_ID = "v1"
_DEFAULT_BUCKET = "ibex-sessions"
_DEFAULT_REGION = "us-east-1"


def _cfg(settings: Any | None = None) -> dict[str, str]:
    """Load S3 config from env, optionally overridden by worker Settings fields."""

    def _pick(env_keys: tuple[str, ...], attr: str | None, default: str = "") -> str:
        if settings is not None and attr:
            val = getattr(settings, attr, None)
            if val is not None and str(val).strip():
                secret = getattr(val, "get_secret_value", None)
                return str(secret() if callable(secret) else val).rstrip("/")
        for key in env_keys:
            raw = os.environ.get(key)
            if raw is not None and raw.strip():
                return raw.rstrip("/") if "ENDPOINT" in key else raw
        return default

    endpoint = _pick(("S3_ENDPOINT",), "s3_endpoint", "")
    return {
        "endpoint": endpoint.rstrip("/") if endpoint else "",
        "access_key": _pick(("S3_ACCESS_KEY",), "s3_access_key", ""),
        "secret_key": _pick(("S3_SECRET_KEY",), "s3_secret_key", ""),
        "bucket": _pick(("S3_BUCKET_SESSIONS",), "s3_bucket_sessions", _DEFAULT_BUCKET)
        or _DEFAULT_BUCKET,
        "region": _pick(("S3_REGION",), "s3_region", _DEFAULT_REGION) or _DEFAULT_REGION,
        "master_key_b64": _pick(
            ("S3_MASTER_KEY_B64", "OBJECTSTORE_MASTER_KEY_B64"),
            "s3_master_key_b64",
            "",
        ),
        "key_id": _pick(("S3_ENCRYPTION_KEY_ID",), "s3_encryption_key_id", _DEFAULT_KEY_ID)
        or _DEFAULT_KEY_ID,
    }


def _escape_key_path(key: str) -> str:
    """Percent-encode each path segment; preserve '/' separators (Go escapeKeyPath)."""
    return "/".join(quote(part, safe="") for part in key.lstrip("/").split("/"))


def _object_url(cfg: dict[str, str], key: str) -> str:
    return f"{cfg['endpoint']}/{cfg['bucket']}/{_escape_key_path(key)}"


def delete_org_prefix(org_id: str, *, settings: Any | None = None) -> None:
    cfg = _cfg(settings)
    if not cfg["endpoint"]:
        raise RuntimeError("S3_ENDPOINT unset")
    prefix = f"{org_id}/"
    for key in _list_keys(cfg, prefix):
        _delete_key(cfg, key)


def delete_uri(uri: str, *, settings: Any | None = None) -> None:
    if not uri.startswith("s3://"):
        raise ValueError("unsupported uri")
    rest = uri[len("s3://") :]
    slash = rest.find("/")
    if slash < 1:
        raise ValueError("malformed uri")
    bucket, key = rest[:slash], rest[slash + 1 :]
    cfg = _cfg(settings)
    if not cfg["endpoint"]:
        raise RuntimeError("S3_ENDPOINT unset")
    if bucket != cfg["bucket"]:
        raise ValueError("bucket mismatch")
    _delete_key(cfg, key)


def put_encrypted_json(key: str, plaintext: bytes, *, settings: Any | None = None) -> str:
    """Seal plaintext (AES-256-GCM envelope) and PUT ArchivedBlob JSON; return s3 URI."""
    cfg = _cfg(settings)
    if not cfg["endpoint"]:
        raise RuntimeError("S3_ENDPOINT unset")
    master = _parse_master_key(cfg["master_key_b64"])
    envelope = _seal_archived_blob(master, cfg["key_id"], plaintext)
    body = json.dumps(envelope).encode()
    url = _object_url(cfg, key)
    headers = {"Content-Type": "application/json"}
    _sign_and_request("PUT", url, cfg, body=body, extra_headers=headers)
    return f"s3://{cfg['bucket']}/{key.lstrip('/')}"


def _parse_master_key(encoded: str) -> bytes:
    if not encoded:
        raise RuntimeError("S3_MASTER_KEY_B64 or OBJECTSTORE_MASTER_KEY_B64 required")
    try:
        raw = base64.b64decode(encoded, validate=False)
    except Exception as exc:
        raise RuntimeError("invalid master key encoding") from exc
    if len(raw) != _DEK_SIZE:
        raise RuntimeError("master key must be 32 bytes")
    return raw


def _gcm_seal(key: bytes, plaintext: bytes) -> bytes:
    nonce = secrets.token_bytes(_NONCE_SIZE)
    ct = AESGCM(key).encrypt(nonce, plaintext, None)
    return nonce + ct


def _seal_archived_blob(master: bytes, key_id: str, plaintext: bytes) -> dict[str, str]:
    if not key_id:
        raise RuntimeError("encryption key id required")
    dek = secrets.token_bytes(_DEK_SIZE)
    ciphertext = _gcm_seal(dek, plaintext)
    wrapped = _gcm_seal(master, dek)
    return {
        "ciphertext_b64": base64.b64encode(ciphertext).decode(),
        "wrapped_dek_b64": base64.b64encode(wrapped).decode(),
        "key_id": key_id,
    }


def _list_keys(cfg: dict[str, str], prefix: str) -> list[str]:
    keys: list[str] = []
    continuation = ""
    while True:
        page_keys, continuation = _list_page(cfg, prefix, continuation)
        keys.extend(page_keys)
        if not continuation:
            return keys


def _list_page(cfg: dict[str, str], prefix: str, continuation: str) -> tuple[list[str], str]:
    q = f"list-type=2&prefix={quote(prefix)}"
    if continuation:
        q += f"&continuation-token={quote(continuation)}"
    url = f"{cfg['endpoint']}/{cfg['bucket']}?{q}"
    resp = _sign_and_request("GET", url, cfg)
    if resp.status_code >= 300:
        raise RuntimeError(f"s3 list {prefix}: {resp.status_code}")
    return _parse_list_xml(resp.text)


def _parse_list_xml(text: str) -> tuple[list[str], str]:
    keys: list[str] = []
    start = 0
    while True:
        i = text.find("<Key>", start)
        if i < 0:
            break
        j = text.find("</Key>", i)
        keys.append(text[i + 5 : j])
        start = j + 6
    if "istruncated>true" not in text.lower():
        return keys, ""
    ti = text.find("<NextContinuationToken>")
    if ti < 0:
        return keys, ""
    tj = text.find("</NextContinuationToken>", ti)
    return keys, text[ti + len("<NextContinuationToken>") : tj]


def _delete_key(cfg: dict[str, str], key: str) -> None:
    url = _object_url(cfg, key)
    resp = _sign_and_request("DELETE", url, cfg)
    if resp.status_code >= 300 and resp.status_code != 404:
        raise RuntimeError(f"s3 delete {key}: {resp.status_code}")


def _sign_and_request(
    method: str,
    url: str,
    cfg: dict[str, str],
    *,
    body: bytes | None = None,
    extra_headers: dict[str, str] | None = None,
) -> httpx.Response:
    parsed = urlparse(url)
    now = datetime.now(UTC)
    amz_date = now.strftime("%Y%m%dT%H%M%SZ")
    date_stamp = now.strftime("%Y%m%d")
    payload_hash = "UNSIGNED-PAYLOAD"
    hdrs: dict[str, str] = {
        "host": parsed.netloc,
        "x-amz-date": amz_date,
        "x-amz-content-sha256": payload_hash,
    }
    if extra_headers:
        for k, v in extra_headers.items():
            hdrs[k.lower()] = v
    if body is not None:
        hdrs["content-length"] = str(len(body))
    signed_keys = sorted(hdrs)
    canonical_headers = "".join(f"{k}:{hdrs[k].strip()}\n" for k in signed_keys)
    signed_headers = ";".join(signed_keys)
    canonical_request = "\n".join(
        [
            method,
            parsed.path or "/",
            parsed.query,
            canonical_headers,
            signed_headers,
            payload_hash,
        ]
    )
    scope = f"{date_stamp}/{cfg['region']}/s3/aws4_request"
    cr_hash = hashlib.sha256(canonical_request.encode()).hexdigest()
    string_to_sign = f"AWS4-HMAC-SHA256\n{amz_date}\n{scope}\n{cr_hash}"
    signing_key = _signing_key(cfg["secret_key"], date_stamp, cfg["region"], "s3")
    signature = hmac.new(signing_key, string_to_sign.encode(), hashlib.sha256).hexdigest()
    auth = (
        f"AWS4-HMAC-SHA256 Credential={cfg['access_key']}/{scope}, "
        f"SignedHeaders={signed_headers}, Signature={signature}"
    )
    out_headers = {k: v for k, v in hdrs.items() if k != "host"}
    out_headers["Authorization"] = auth
    return httpx.request(method, url, content=body, headers=out_headers, timeout=30.0)


def _signing_key(secret: str, date: str, region: str, service: str) -> bytes:
    def _hm(key: bytes, msg: str) -> bytes:
        return hmac.new(key, msg.encode(), hashlib.sha256).digest()

    k_date = _hm(("AWS4" + secret).encode(), date)
    k_region = _hm(k_date, region)
    k_service = _hm(k_region, service)
    return _hm(k_service, "aws4_request")
