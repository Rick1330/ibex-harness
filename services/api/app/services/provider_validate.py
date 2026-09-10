"""Validate provider API keys against upstream before Auth store."""

from __future__ import annotations

import ipaddress
import logging
import socket
from typing import Final
from urllib.parse import urlparse

import httpx
from apierror_py import INVALID_CREDENTIAL

from app.errors import ApiError

logger = logging.getLogger(__name__)

_VALIDATE_TIMEOUT = httpx.Timeout(5.0, connect=5.0)
_AZURE_API_VERSION = "2024-02-01"
_DEFAULT_BASES: Final[dict[str, str]] = {
    "openai": "https://api.openai.com",
    "anthropic": "https://api.anthropic.com",
    "bedrock": "https://api.openai.com",
    "vllm_self_hosted": "http://127.0.0.1:8000",
}
_CLOUD_DEFAULT_HOSTS: Final[dict[str, frozenset[str]]] = {
    "openai": frozenset({"api.openai.com"}),
    "anthropic": frozenset({"api.anthropic.com"}),
    "bedrock": frozenset({"api.openai.com"}),
}
_INVALID_MSG = "Provider key validation failed"


def _invalid() -> ApiError:
    return ApiError(code=INVALID_CREDENTIAL, message=_INVALID_MSG)


async def validate_provider_credential(
    *,
    provider_name: str,
    api_key: str,
    base_url: str | None = None,
    client: httpx.AsyncClient | None = None,
) -> None:
    """Probe upstream models endpoint; raise INVALID_CREDENTIAL on failure."""
    url = _models_url(provider_name, base_url)
    _assert_probe_destination(provider_name, url)
    headers = _auth_headers(provider_name, api_key)
    status = await _probe_models(url, headers, client)
    if status < 200 or status >= 300:
        logger.info("provider key probe rejected provider=%s status=%s", provider_name, status)
        raise _invalid()


def _models_url(provider_name: str, base_url: str | None) -> str:
    if provider_name == "azure_openai":
        base = (base_url or "").rstrip("/")
        if not base:
            raise _invalid()
        return f"{base}/openai/models?api-version={_AZURE_API_VERSION}"
    base = (base_url or _DEFAULT_BASES.get(provider_name, "")).rstrip("/")
    if not base:
        raise _invalid()
    return f"{base}/v1/models"


def _assert_probe_destination(provider_name: str, url: str) -> None:
    parsed = urlparse(url)
    host = (parsed.hostname or "").lower().rstrip(".")
    if not host or parsed.scheme not in {"http", "https"}:
        raise _invalid()
    if provider_name == "vllm_self_hosted":
        _assert_self_hosted_destination(parsed.scheme, host)
        return
    if parsed.scheme != "https":
        raise _invalid()
    if provider_name == "azure_openai":
        if not (host.endswith(".openai.azure.com") or host == "openai.azure.com"):
            raise _invalid()
        _assert_public_resolved_host(host)
        return
    allowed = _CLOUD_DEFAULT_HOSTS.get(provider_name, frozenset())
    if host in allowed:
        return
    # Custom HTTPS base for cloud providers: no private/reserved destinations.
    _assert_public_resolved_host(host)


def _assert_self_hosted_destination(scheme: str, host: str) -> None:
    if scheme == "https":
        return
    if scheme != "http":
        raise _invalid()
    if host in {"localhost"} or _is_mesh_short_name(host):
        return
    try:
        ip = ipaddress.ip_address(host)
    except ValueError:
        addrs = _resolved_addrs(host)
        # Non-literal host over HTTP must resolve to loopback/private only.
        if not addrs or not all(addr.is_loopback or addr.is_private for addr in addrs):
            raise _invalid() from None
        return
    if not (ip.is_loopback or ip.is_private):
        raise _invalid()


def _assert_public_resolved_host(host: str) -> None:
    try:
        ip = ipaddress.ip_address(host)
    except ValueError:
        addrs = _resolved_addrs(host)
        if not addrs or any(_is_blocked_addr(a) for a in addrs):
            raise _invalid() from None
        return
    if _is_blocked_addr(ip):
        raise _invalid()


def _resolved_addrs(host: str) -> list[ipaddress.IPv4Address | ipaddress.IPv6Address]:
    try:
        infos = socket.getaddrinfo(host, None)
    except socket.gaierror:
        return []
    out: list[ipaddress.IPv4Address | ipaddress.IPv6Address] = []
    for info in infos:
        try:
            out.append(ipaddress.ip_address(info[4][0]))
        except (ValueError, IndexError):
            continue
    return out


def _is_blocked_addr(addr: ipaddress.IPv4Address | ipaddress.IPv6Address) -> bool:
    return bool(
        addr.is_private
        or addr.is_loopback
        or addr.is_link_local
        or addr.is_reserved
        or addr.is_multicast
        or addr.is_unspecified
    )


def _is_mesh_short_name(host: str) -> bool:
    return "." not in host and host.replace("-", "").isalnum()


async def _probe_models(
    url: str,
    headers: dict[str, str],
    client: httpx.AsyncClient | None,
) -> int:
    owns_client = client is None
    http = client or httpx.AsyncClient(
        timeout=_VALIDATE_TIMEOUT,
        follow_redirects=False,
    )
    try:
        resp = await http.get(url, headers=headers)
    except httpx.HTTPError:
        logger.info("provider key probe transport failure")
        raise _invalid() from None
    finally:
        if owns_client:
            await http.aclose()
    return resp.status_code


def _auth_headers(provider_name: str, api_key: str) -> dict[str, str]:
    if provider_name == "anthropic":
        return {
            "x-api-key": api_key,
            "anthropic-version": "2023-06-01",
        }
    if provider_name == "azure_openai":
        return {"api-key": api_key}
    return {"Authorization": f"Bearer {api_key}"}
