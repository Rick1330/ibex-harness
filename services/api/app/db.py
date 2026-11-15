"""Async SQLAlchemy helpers for the management API (RLS org GUC)."""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from dataclasses import dataclass

from ibex_async_db import normalize_async_database_url, parse_async_database_url
from sqlalchemy import text
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from app.config import Settings

# Compose/CI connect as role ``ibex`` (often superuser). Superusers bypass RLS
# even with FORCE ROW LEVEL SECURITY — switch to ``ibex_app`` for enforcement.
_SET_APP_ROLE_SQL = "SET LOCAL ROLE ibex_app"
_CLEAR_SERVICE_ACCOUNT_SQL = "SELECT set_config('app.is_service_account', 'false', true)"
_ORG_GUC_SQL = "SELECT set_config('app.current_org_id', :org_id, true)"

# The capability login the API must connect as. A module constant, not a
# setting: the DSN already names the login, and a second configurable source
# would let the assertion below be reconfigured to match a mistake.
CAPABILITY_LOGIN = "ibex_runtime"
# The migration owner. Every service must stay off it: the tenancy guarantee
# rests on the connection not being able to bypass RLS.
OWNER_LOGIN = "ibex"

# Reports the effective and session logins plus whether either is a superuser.
# COALESCE(..., true) fails closed: a login that cannot be resolved in pg_roles
# is treated as privileged.
_LOGIN_PROBE_SQL = """
    SELECT current_user, session_user,
           COALESCE((SELECT rolsuper FROM pg_roles WHERE rolname = current_user), true),
           COALESCE((SELECT rolsuper FROM pg_roles WHERE rolname = session_user), true)"""


class CapabilityLoginError(RuntimeError):
    """The pool login is not the capability login this service requires."""


@dataclass(frozen=True, slots=True)
class _LoginFacts:
    """The login identity the probe read back from PostgreSQL."""

    current: str
    session: str
    current_super: bool
    session_super: bool


async def _read_login_facts(engine: AsyncEngine) -> _LoginFacts:
    """Read the effective and session login plus their superuser flags."""
    async with engine.connect() as conn:
        row = (
            await conn.execute(
                text(  # nosemgrep: python.sqlalchemy.security.audit.avoid-sqlalchemy-text.avoid-sqlalchemy-text
                    _LOGIN_PROBE_SQL
                )
            )
        ).one()
    current, session, current_super, session_super = row
    return _LoginFacts(current, session, current_super, session_super)


def _login_violation(facts: _LoginFacts) -> str | None:
    """Return the startup error for a privileged or unexpected login, else ``None``."""
    if facts.current == OWNER_LOGIN or facts.session == OWNER_LOGIN:
        return (
            f"api: connection login is {OWNER_LOGIN!r}, the owner login; "
            f"api must connect as the {CAPABILITY_LOGIN!r} capability login, "
            "never the RLS-bypassing owner"
        )
    if facts.current_super or facts.session_super:
        return (
            f"api: connection login {facts.session!r} (current_user {facts.current!r}) "
            "is a superuser; "
            f"api must connect as the non-superuser {CAPABILITY_LOGIN!r} capability login"
        )
    if facts.current != CAPABILITY_LOGIN:
        return (
            f"api: connection login is {facts.current!r}, want the {CAPABILITY_LOGIN!r} "
            "capability login; the DSN names the login and the expected value is compiled in"
        )
    return None


async def assert_capability_login(engine: AsyncEngine) -> None:
    """Fail unless the pool connects as ``ibex_runtime``, not owner, not superuser.

    A wrong password already fails loudly when the pool connects. A wrong login
    starts silently and re-enables the RLS bypass the tenancy guarantee rests on
    (the owner is a superuser, and ``FORCE ROW LEVEL SECURITY`` does not cover
    superusers), so it fails startup here instead. Runs once when the pool is
    first checked at startup, never per request, and never echoes the DSN.
    """
    violation = _login_violation(await _read_login_facts(engine))
    if violation is not None:
        raise CapabilityLoginError(violation)


def create_engine(settings: Settings) -> AsyncEngine:
    dsn = settings.database_url
    if not dsn:
        raise RuntimeError("IBEX_API_DATABASE_URL is required for database access")
    parsed = parse_async_database_url(dsn)
    return create_async_engine(
        parsed.url,
        pool_pre_ping=True,
        connect_args=dict(parsed.connect_args),
        # A DBAPIError's rendered message carries the failing statement and its
        # bound parameters; with memory content, tokens and provider secrets
        # among them, that text must never reach a log line or a span event.
        # Masking at the driver covers every log site, including tracebacks
        # rendered by libraries we do not control.
        hide_parameters=True,
    )


def create_session_factory(engine: AsyncEngine) -> async_sessionmaker[AsyncSession]:
    return async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)


async def _bind_org_guc(session: AsyncSession, org_id: str) -> None:
    # Bound parameter — not string-interpolated SQL.
    await session.execute(
        text(_SET_APP_ROLE_SQL),  # nosemgrep: python.sqlalchemy.security.audit.avoid-sqlalchemy-text.avoid-sqlalchemy-text
    )
    await session.execute(
        text(_CLEAR_SERVICE_ACCOUNT_SQL),  # nosemgrep: python.sqlalchemy.security.audit.avoid-sqlalchemy-text.avoid-sqlalchemy-text
    )
    await session.execute(
        text(_ORG_GUC_SQL),  # nosemgrep: python.sqlalchemy.security.audit.avoid-sqlalchemy-text.avoid-sqlalchemy-text
        {"org_id": org_id},
    )


@asynccontextmanager
async def session_with_org(
    factory: async_sessionmaker[AsyncSession],
    org_id: str,
) -> AsyncIterator[AsyncSession]:
    """Yield a transactional session with ``app.current_org_id`` bound for RLS."""
    async with factory() as session:
        try:
            async with session.begin():
                await _bind_org_guc(session, org_id)
                yield session
        except Exception:
            await session.rollback()
            raise


__all__ = [
    "CAPABILITY_LOGIN",
    "OWNER_LOGIN",
    "CapabilityLoginError",
    "assert_capability_login",
    "create_engine",
    "create_session_factory",
    "normalize_async_database_url",
    "parse_async_database_url",
    "session_with_org",
]
