"""Validate provider API keys against upstream before Auth store."""

from __future__ import annotations

import asyncio
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
_VALIDATE_DEADLINE = 5.0
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
_IPAddr = ipaddress.IPv4Address | ipaddress.IPv6Address


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
    try:
        async with asyncio.timeout(_VALIDATE_DEADLINE):
            url = _models_url(provider_name, base_url)
            await _assert_probe_destination(provider_name, url)
            headers = _auth_headers(provider_name, api_key)
            status = await _probe_models(url, headers, client)
    except TimeoutError:
        logger.info("provider key probe deadline exceeded")
        raise _invalid() from None
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


async def _assert_probe_destination(provider_name: str, url: str) -> None:
    parsed = urlparse(url)
    host = (parsed.hostname or "").lower().rstrip(".")
    if not host or parsed.scheme not in {"http", "https"}:
        raise _invalid()
    if provider_name == "vllm_self_hosted":
        await _assert_self_hosted_destination(parsed.scheme, host)
        return
    await _assert_cloud_destination(provider_name, parsed.scheme, host)


async def _assert_cloud_destination(provider_name: str, scheme: str, host: str) -> None:
    if scheme != "https":
        raise _invalid()
    if provider_name == "azure_openai":
        await _assert_azure_host(host)
        return
    if host in _CLOUD_DEFAULT_HOSTS.get(provider_name, frozenset()):
        return
    await _assert_public_resolved_host(host)


async def _assert_azure_host(host: str) -> None:
    if not (host.endswith(".openai.azure.com") or host == "openai.azure.com"):
        raise _invalid()
    await _assert_public_resolved_host(host)


async def _assert_self_hosted_destination(scheme: str, host: str) -> None:
    if scheme == "https":
        return
    if scheme != "http":
        raise _invalid()
    # Plaintext HTTP is allowed only for literal loopback addresses.
    literal = _literal_ip(host)
    if literal is None or not literal.is_loopback:
        raise _invalid()


async def _assert_public_resolved_host(host: str) -> None:
    literal = _literal_ip(host)
    if literal is not None:
        if _is_blocked_addr(literal):
            raise _invalid()
        return
    addrs = await _resolved_addrs(host)
    if not addrs or any(_is_blocked_addr(a) for a in addrs):
        raise _invalid()


def _literal_ip(host: str) -> _IPAddr | None:
    try:
        return ipaddress.ip_address(host)
    except ValueError:
        return None


async def _resolved_addrs(host: str) -> list[_IPAddr]:
    try:
        infos = await asyncio.to_thread(socket.getaddrinfo, host, None)
    except socket.gaierror:
        return []
    out: list[_IPAddr] = []
    for info in infos:
        try:
            out.append(ipaddress.ip_address(info[4][0]))
        except (ValueError, IndexError):
            continue
    return out


def _is_blocked_addr(addr: _IPAddr) -> bool:
    return bool(
        addr.is_private
        or addr.is_loopback
        or addr.is_link_local
        or addr.is_reserved
        or addr.is_multicast
        or addr.is_unspecified
    )


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
        async with http.stream("GET", url, headers=headers) as resp:
            return resp.status_code
    except httpx.HTTPError:
        logger.info("provider key probe transport failure")
        raise _invalid() from None
    finally:
        if owns_client:
            await http.aclose()


def _auth_headers(provider_name: str, api_key: str) -> dict[str, str]:
    if provider_name == "anthropic":
        return {
            "x-api-key": api_key,
            "anthropic-version": "2023-06-01",
        }
    if provider_name == "azure_openai":
        return {"api-key": api_key}
    return {"Authorization": f"Bearer {api_key}"}
