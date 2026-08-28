"""Trust checks for insecure Auth gRPC dial targets."""

from __future__ import annotations

import ipaddress

_LOOPBACK_DNS = frozenset({"localhost"})


def assert_trusted_insecure_auth_target(target: str) -> str:
    cleaned = target.strip()
    if not cleaned:
        raise ValueError("auth gRPC target is required")
    host = _host_of(cleaned)
    if _is_trusted_insecure_host(host):
        return cleaned
    raise ValueError(
        "insecure Auth gRPC requires loopback/private address or mesh short name; "
        f"refusing target host {host!r}"
    )


def _host_of(target: str) -> str:
    cleaned = _strip_grpc_uri_prefix(target.strip())
    bracketed = _host_from_brackets(cleaned)
    if bracketed is not None:
        return bracketed
    return _host_from_hostport(cleaned)


def _strip_grpc_uri_prefix(target: str) -> str:
    lowered = target.lower()
    for prefix in ("dns:///", "dns://", "ipv4:", "ipv6:"):
        if lowered.startswith(prefix):
            return target[len(prefix) :]
    return target


def _host_from_brackets(target: str) -> str | None:
    if not target.startswith("["):
        return None
    end = target.find("]")
    if end <= 0:
        return None
    return target[1:end].lower().rstrip(".")


def _host_from_hostport(target: str) -> str:
    host, _, port = target.rpartition(":")
    if host and port.isdigit():
        return host.lower().rstrip(".")
    return target.lower().rstrip(".")


def _is_trusted_insecure_host(host: str) -> bool:
    if not host:
        return False
    if host in _LOOPBACK_DNS:
        return True
    if "." not in host and host.replace("-", "").isalnum():
        return True
    try:
        ip = ipaddress.ip_address(host)
    except ValueError:
        return False
    return bool(ip.is_loopback or ip.is_private)
