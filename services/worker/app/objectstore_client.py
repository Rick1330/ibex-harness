"""Minimal S3-compatible helpers for org-deletion objectstore stage (4.P.3)."""

from __future__ import annotations

import hashlib
import hmac
import logging
import os
from datetime import UTC, datetime
from urllib.parse import quote, urlparse

import httpx

logger = logging.getLogger(__name__)


def _cfg() -> dict[str, str]:
    return {
        "endpoint": (os.environ.get("S3_ENDPOINT") or "").rstrip("/"),
        "access_key": os.environ.get("S3_ACCESS_KEY") or "",
        "secret_key": os.environ.get("S3_SECRET_KEY") or "",
        "bucket": os.environ.get("S3_BUCKET_SESSIONS") or "ibex-sessions",
        "region": os.environ.get("S3_REGION") or "us-east-1",
    }


def delete_org_prefix(org_id: str) -> None:
    cfg = _cfg()
    if not cfg["endpoint"]:
        return
    prefix = f"{org_id}/"
    for key in _list_keys(cfg, prefix):
        _delete_key(cfg, key)


def delete_uri(uri: str) -> None:
    if not uri.startswith("s3://"):
        raise ValueError("unsupported uri")
    rest = uri[len("s3://") :]
    slash = rest.find("/")
    if slash < 1:
        raise ValueError("malformed uri")
    bucket, key = rest[:slash], rest[slash + 1 :]
    cfg = _cfg()
    if bucket != cfg["bucket"]:
        raise ValueError("bucket mismatch")
    _delete_key(cfg, key)


def put_encrypted_json(key: str, body: bytes) -> str:
    """Put JSON envelope bytes; returns s3://bucket/key."""
    cfg = _cfg()
    if not cfg["endpoint"]:
        raise RuntimeError("S3_ENDPOINT unset")
    url = f"{cfg['endpoint']}/{cfg['bucket']}/{key.lstrip('/')}"
    headers = {"Content-Type": "application/json"}
    _sign_and_request("PUT", url, cfg, body=body, extra_headers=headers)
    return f"s3://{cfg['bucket']}/{key.lstrip('/')}"


def _list_keys(cfg: dict[str, str], prefix: str) -> list[str]:
    keys: list[str] = []
    token = ""
    while True:
        q = f"list-type=2&prefix={quote(prefix)}"
        if token:
            q += f"&continuation-token={quote(token)}"
        url = f"{cfg['endpoint']}/{cfg['bucket']}?{q}"
        resp = _sign_and_request("GET", url, cfg)
        text = resp.text
        start = 0
        while True:
            i = text.find("<Key>", start)
            if i < 0:
                break
            j = text.find("</Key>", i)
            keys.append(text[i + 5 : j])
            start = j + 6
        truncated = "<IsTruncated>true</IsTruncated>" in text.lower().replace(
            "istruncated>true", "istruncated>true"
        )
        # Case-insensitive truncated check
        truncated = "istruncated>true" in text.lower()
        if not truncated:
            break
        ti = text.find("<NextContinuationToken>")
        if ti < 0:
            break
        tj = text.find("</NextContinuationToken>", ti)
        token = text[ti + len("<NextContinuationToken>") : tj]
    return keys


def _delete_key(cfg: dict[str, str], key: str) -> None:
    url = f"{cfg['endpoint']}/{cfg['bucket']}/{key.lstrip('/')}"
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
    string_to_sign = "\n".join(["AWS4-HMAC-SHA256", amz_date, scope, cr_hash])
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
