"""Map libpq-style PostgreSQL DSNs to asyncpg SQLAlchemy URLs."""

from __future__ import annotations

import ssl
from dataclasses import dataclass, field
from typing import Mapping
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

_SSL_QUERY_KEYS = frozenset({"sslmode", "sslrootcert", "sslcert", "sslkey", "sslcrl"})
_TLS_MATERIAL_KEYS = ("sslrootcert", "sslcert", "sslkey")
_PG_SCHEME = "postgresql://"
_ASYNCPG_SCHEME = "postgresql+asyncpg://"
_PLAINTEXT_SSLMODES = frozenset({"disable", "allow"})
_VERIFIED_SSLMODES = frozenset({"require", "verify-ca", "verify-full"})


@dataclass(frozen=True, slots=True)
class AsyncDatabaseTarget:
    """SQLAlchemy asyncpg URL plus driver connect_args (SSL)."""

    url: str
    connect_args: Mapping[str, object] = field(default_factory=dict)


def parse_async_database_url(url: str) -> AsyncDatabaseTarget:
    """Map libpq-style DSNs to asyncpg URL + ssl connect_args.

    ``sslmode`` is not a valid asyncpg connect kwarg when SQLAlchemy parses the
    URL, so it is translated into ``connect_args["ssl"]`` and removed from the
    query string. Encrypting modes always use a verified TLS context (hostname
    + certificate checks); weaker libpq ``require`` semantics are intentionally
    strengthened.
    """
    raw = url.strip()
    if raw.startswith("postgres://"):
        raw = _PG_SCHEME + raw[len("postgres://") :]
    if raw.startswith(_PG_SCHEME):
        raw = _ASYNCPG_SCHEME + raw[len(_PG_SCHEME) :]

    parts = urlsplit(raw)
    query = dict(parse_qsl(parts.query, keep_blank_values=True))
    sslmode = query.pop("sslmode", None)
    ssl_arg = _ssl_connect_arg(sslmode, query)
    for key in _SSL_QUERY_KEYS:
        query.pop(key, None)

    cleaned = urlunsplit(
        (parts.scheme, parts.netloc, parts.path, urlencode(list(query.items())), parts.fragment)
    )
    connect_args: dict[str, object] = {}
    if ssl_arg is not None:
        connect_args["ssl"] = ssl_arg
    return AsyncDatabaseTarget(url=cleaned, connect_args=connect_args)


def normalize_async_database_url(url: str) -> str:
    """Return the asyncpg SQLAlchemy URL with libpq SSL params removed."""
    return parse_async_database_url(url).url


def _ssl_connect_arg(
    sslmode: str | None, query: dict[str, str]
) -> bool | str | ssl.SSLContext | None:
    if sslmode is None:
        return None
    mode = sslmode.lower()
    if mode == "prefer":
        return "prefer"
    if mode in _PLAINTEXT_SSLMODES:
        return False
    if mode not in _VERIFIED_SSLMODES:
        msg = f"unsupported sslmode: {sslmode!r}"
        raise ValueError(msg)
    return _verified_tls_context(query)


def _verified_tls_context(query: dict[str, str]) -> bool | ssl.SSLContext:
    if not _has_tls_material(query):
        return True
    return _build_tls_context(query)


def _has_tls_material(query: dict[str, str]) -> bool:
    return any(query.get(key) for key in _TLS_MATERIAL_KEYS)


def _build_tls_context(query: dict[str, str]) -> ssl.SSLContext:
    ctx = ssl.create_default_context(cafile=query.get("sslrootcert"))
    ctx.minimum_version = ssl.TLSVersion.TLSv1_2
    certfile = query.get("sslcert")
    keyfile = query.get("sslkey")
    if certfile and keyfile:
        ctx.load_cert_chain(certfile, keyfile=keyfile)
    return ctx
