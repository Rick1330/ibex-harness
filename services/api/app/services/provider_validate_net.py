"""Network helpers for provider credential validate probes."""

from __future__ import annotations

import asyncio
import ipaddress
import socket

from apierror_py import INVALID_CREDENTIAL

from app.errors import ApiError

_IPAddr = ipaddress.IPv4Address | ipaddress.IPv6Address
_INVALID_MSG = "Provider key validation failed"


def invalid() -> ApiError:
    return ApiError(code=INVALID_CREDENTIAL, message=_INVALID_MSG)


async def assert_public_resolved_host(host: str) -> None:
    literal = literal_ip(host)
    if literal is not None:
        if is_blocked_addr(literal):
            raise invalid()
        return
    addrs = await resolved_addrs(host)
    if not addrs or any(is_blocked_addr(a) for a in addrs):
        raise invalid()


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
