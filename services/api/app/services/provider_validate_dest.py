"""Destination checks for provider credential validate probes."""

from __future__ import annotations

import asyncio
import ipaddress
import socket
from urllib.parse import urlparse

from apierror_py import INVALID_CREDENTIAL

from app.errors import ApiError

_IPAddr = ipaddress.IPv4Address | ipaddress.IPv6Address
_CLOUD_DEFAULT_HOSTS: dict[str, frozenset[str]] = {
    "openai": frozenset({"api.openai.com"}),
    "anthropic": frozenset({"api.anthropic.com"}),
    "bedrock": frozenset({"api.openai.com"}),
}
_INVALID_MSG = "Provider key validation failed"


def _invalid() -> ApiError:
    return ApiError(code=INVALID_CREDENTIAL, message=_INVALID_MSG)


async def assert_probe_destination(provider_name: str, url: str) -> None:
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
    await assert_public_resolved_host(host)


async def _assert_azure_host(host: str) -> None:
    if not (host.endswith(".openai.azure.com") or host == "openai.azure.com"):
        raise _invalid()
    await assert_public_resolved_host(host)


async def _assert_self_hosted_destination(scheme: str, host: str) -> None:
    if scheme not in {"http", "https"}:
        raise _invalid()
    # Both plaintext and TLS self-hosted probes are limited to literal loopback.
    literal = literal_ip(host)
    if literal is None or not literal.is_loopback:
        raise _invalid()


async def assert_public_resolved_host(host: str) -> None:
    literal = literal_ip(host)
    if literal is not None:
        if is_blocked_addr(literal):
            raise _invalid()
        return
    addrs = await resolved_addrs(host)
    if not addrs or any(is_blocked_addr(a) for a in addrs):
        raise _invalid()


def literal_ip(host: str) -> _IPAddr | None:
    try:
        return ipaddress.ip_address(host)
    except ValueError:
        return None


async def resolved_addrs(host: str) -> list[_IPAddr]:
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


def is_blocked_addr(addr: _IPAddr) -> bool:
    return bool(
        addr.is_private
        or addr.is_loopback
        or addr.is_link_local
        or addr.is_reserved
        or addr.is_multicast
        or addr.is_unspecified
    )
