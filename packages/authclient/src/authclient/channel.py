"""Shared AuthService gRPC channel factory (ADR-0097 §4).

ADR-0097 §4 requires the AuthService gRPC listener to carry TLS, because it serves
several peers and cannot be co-located behind the loopback boundary the other
internal hops rely on. Every Python AuthService dialer therefore goes through
:func:`open_auth_channel`:

* ``IBEX_AUTH_GRPC_CA_FILE`` set -> TLS with that CA bundle as the only root of trust.
* unset -> an insecure channel, still gated by
  :func:`authclient.target.assert_trusted_insecure_auth_target`.

Keeping the decision in one place means a service cannot accidentally dial
AuthService over plaintext while the deployment expects TLS, and the insecure
trust gate cannot drift between callers.
"""

from __future__ import annotations

import functools
import re
import ssl
from pathlib import Path

import grpc

from authclient.target import (
    _host_from_brackets,
    _strip_grpc_uri_prefix,
    assert_trusted_insecure_auth_target,
)

_MIN_PORT = 1
_MAX_PORT = 65535


class AuthCAError(ValueError):
    """The configured AuthService CA bundle could not be loaded or parsed.

    Subclasses :class:`ValueError` so existing callers and tests that treat a
    bad CA as a value error keep working, while a caller can translate only this
    class (and leave target-validation errors untouched).
    """

# A CA bundle must carry certificates only. ``grpc.ssl_channel_credentials``
# accepts a combined cert+key PEM but would then hand the private key to the
# TLS stack, so any private-key block is rejected before it reaches gRPC.
_PRIVATE_KEY_BLOCK = re.compile(rb"-----BEGIN [A-Z0-9 ]*PRIVATE KEY-----")

# The parsed bundle is cached by path. The first call happens during service
# startup (the validator/channel construction in the lifespan); every later call
# is a pure memory lookup, so a request handler never performs blocking file I/O.
# A rotated CA is picked up on process restart, matching the Go client.
_CA_CACHE_MAXSIZE = 8


def read_auth_ca(ca_file: str) -> bytes:
    """Read and parse the ``IBEX_AUTH_GRPC_CA_FILE`` PEM bundle.

    The path is trimmed so a padded environment value behaves like the bare path,
    matching the Go client. The bundle must contain at least one parseable X.509
    certificate: a garbage or directive-only file is rejected here rather than at
    request time by :func:`grpc.ssl_channel_credentials`.

    The result is cached by path. Call this once during startup (the service
    lifespans do, through the validator construction); a rotated file requires a
    process restart, which is also how the Go client picks it up.

    Raises :class:`ValueError` when the file is missing, unreadable, empty, or not
    a PEM certificate bundle. The message names the environment variable and the
    path, never the file contents.
    """
    return _load_auth_ca(ca_file.strip())


@functools.lru_cache(maxsize=_CA_CACHE_MAXSIZE)
def _load_auth_ca(path: str) -> bytes:
    """Read and validate one CA bundle; ``path`` is the cache key.

    ``lru_cache`` is thread-safe and does not cache exceptions, so a failed read
    or an invalid bundle is retried on the next call rather than remembered.
    """
    ca_path = Path(path)
    try:
        bundle = ca_path.read_bytes()
    except OSError as exc:
        raise AuthCAError(f"IBEX_AUTH_GRPC_CA_FILE is not readable: {ca_path}") from exc
    if not bundle.strip():
        raise AuthCAError(f"IBEX_AUTH_GRPC_CA_FILE is empty: {ca_path}")
    _assert_pem_certificate_bundle(bundle, ca_path)
    return bundle


def _assert_pem_certificate_bundle(bundle: bytes, path: Path) -> None:
    if _PRIVATE_KEY_BLOCK.search(bundle):
        raise AuthCAError(
            f"IBEX_AUTH_GRPC_CA_FILE must contain certificates only, "
            f"not a private key: {path}"
        )
    try:
        pem = bundle.decode("ascii")
    except UnicodeDecodeError as exc:
        raise AuthCAError(
            f"IBEX_AUTH_GRPC_CA_FILE is not a PEM certificate bundle: {path}"
        ) from exc
    context = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
    try:
        context.load_verify_locations(cadata=pem)
    except (ssl.SSLError, ValueError) as exc:
        raise AuthCAError(
            f"IBEX_AUTH_GRPC_CA_FILE does not contain a certificate: {path}"
        ) from exc


def assert_auth_target(target: str) -> str:
    """Validate a TLS Auth gRPC target and return it trimmed.

    TLS authenticates the server, so the host itself is not restricted the way the
    insecure gate restricts it. The shape still has to be ``host:port``: the
    existing parser handles the ``dns:///``, ``ipv4:`` and ``ipv6:`` prefixes and
    bracketed IPv6 literals.
    """
    cleaned = target.strip()
    if not cleaned:
        raise ValueError("auth gRPC target is required")
    if not _is_valid_port(_port_of(cleaned)):
        raise ValueError(f"auth gRPC target must be host:port; refusing target {cleaned!r}")
    return cleaned


def open_auth_channel(target: str, ca_file: str | None = None) -> grpc.aio.Channel:
    """Open the AuthService channel, TLS when a CA file is configured.

    Returns the channel without awaiting anything: callers await their RPCs on it
    and ``aclose`` it, exactly as before. ``ca_file`` is the value of
    ``IBEX_AUTH_GRPC_CA_FILE``; an empty or whitespace-only string is treated as
    unset, matching the Go client.
    """
    ca_file = ca_file.strip() if ca_file else ""
    if ca_file:
        credentials = grpc.ssl_channel_credentials(root_certificates=read_auth_ca(ca_file))
        return grpc.aio.secure_channel(assert_auth_target(target), credentials)
    # Plaintext is only reachable after the loopback/private trust gate.
    return grpc.aio.insecure_channel(assert_trusted_insecure_auth_target(target))  # nosec B321


def _port_of(target: str) -> str:
    cleaned = _strip_grpc_uri_prefix(target)
    if _host_from_brackets(cleaned) is not None:
        remainder = cleaned[cleaned.find("]") + 1 :]
        return remainder[1:] if remainder.startswith(":") else ""
    host, separator, port = cleaned.rpartition(":")
    return port if separator and host else ""


def _is_valid_port(port: str) -> bool:
    return port.isdigit() and _MIN_PORT <= int(port) <= _MAX_PORT
