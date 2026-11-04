"""The database URL the benchmarks connect with, read from the environment once.

The benches each grew their own copy of this lookup. Keeping the rule here means a new bench
cannot invent another interpretation: the bench-specific variable wins over the general one,
and a `postgres://` URL is rewritten to the async driver the service is configured with.
"""

from __future__ import annotations

import os

_ENV_VARS = ("IBEX_MEMORY_DATABASE_URL", "POSTGRES_TEST_DSN", "POSTGRES_DSN")


def raw_dsn() -> str:
    """The first configured DSN, unmodified. Raises when none is set."""
    for name in _ENV_VARS:
        value = os.getenv(name)
        if value:
            return value
    raise RuntimeError(f"{' or '.join(_ENV_VARS)} required")


def async_dsn() -> str:
    """``raw_dsn`` rewritten for SQLAlchemy's asyncpg driver."""
    return to_asyncpg(raw_dsn())


def to_asyncpg(dsn: str) -> str:
    if dsn.startswith("postgres://"):
        return "postgresql+asyncpg://" + dsn[len("postgres://") :]
    if dsn.startswith("postgresql://") and "+asyncpg" not in dsn.split("://", 1)[0]:
        return "postgresql+asyncpg://" + dsn[len("postgresql://") :]
    return dsn
