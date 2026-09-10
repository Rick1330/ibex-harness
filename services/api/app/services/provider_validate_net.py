"""Network helpers for provider credential validate probes."""

from __future__ import annotations

import asyncio
import ipaddress
import socket
from dataclasses import dataclass
from urllib.parse import urlparse, urlunparse

from apierror_py import INVALID_CREDENTIAL

from app.errors import ApiError

_IPAddr = ipaddress.IPv4Address | ipaddress.IPv6Address
_INVALID_MSG = "Provider key validation failed"


@dataclass(frozen=True)
class ProbeDial:
    """Validated dial target: connect to connect_ip, TLS/Host use server_name."""

    server_name: str
    connect_ip: str | None  # None → leave URL host unchanged (allowlisted hosts)


def invalid() -> ApiError:
    return ApiError(code=INVALID_CREDENTIAL, message=_INVALID_MSG)


async def assert_public_resolved_host(host: str) -> ProbeDial:
    """Resolve once, reject non-public addrs, return pin for the outbound dial."""
    literal = literal_ip(host)
    if literal is not None:
        if is_blocked_addr(literal):
            raise invalid()
        return ProbeDial(server_name=host, connect_ip=str(literal))
    addrs = await resolved_addrs(host)
    if not addrs or any(is_blocked_addr(a) for a in addrs):
        raise invalid()
    return ProbeDial(server_name=host, connect_ip=str(addrs[0]))


def url_for_dial(url: str, dial: ProbeDial) -> str:
    """Rewrite URL host to the validated connect_ip when pinning is required."""
    if dial.connect_ip is None:
        return url
    parsed = urlparse(url)
    host = dial.connect_ip
    if ":" in host and not host.startswith("["):
        host = f"[{host}]"
    netloc = host if parsed.port is None else f"{host}:{parsed.port}"
    return urlunparse(parsed._replace(netloc=netloc))


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
