"""Startup assertion that the memory pool connects as its capability login.

The v1 profile connects memory on ``ibex_runtime``. A wrong *password* fails
loudly at connect; a wrong *login* starts silently and quietly re-enables the
RLS bypass the tenancy claim rests on, because the owner login is a superuser
and ``FORCE ROW LEVEL SECURITY`` does not cover superusers. This module makes
that failure a startup failure.

It mirrors ``services/proxy/internal/bootstrap/postgres.go`` and the equivalent
helpers in ``services/api/app/db.py`` and ``services/worker/app/db.py``: one
query at startup, three checks in order (not the owner, not a superuser, is the
expected login), never per request.
"""

from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine

# The capability login the memory service must connect as. A module constant,
# not a setting: the DSN already names the login, and a second configurable
# source would let the assertion below be reconfigured to match a mistake.
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
            f"memory: connection login is {OWNER_LOGIN!r}, the owner login; "
            f"memory must connect as the {CAPABILITY_LOGIN!r} capability login, "
            "never the RLS-bypassing owner"
        )
    if facts.current_super or facts.session_super:
        return (
            f"memory: connection login {facts.session!r} "
            f"(current_user {facts.current!r}) is a superuser; "
            f"memory must connect as the non-superuser {CAPABILITY_LOGIN!r} capability login"
        )
    if facts.current != CAPABILITY_LOGIN:
        return (
            f"memory: connection login is {facts.current!r}, want the {CAPABILITY_LOGIN!r} "
            "capability login; the DSN names the login and the expected value is compiled in"
        )
    return None


async def assert_capability_login(engine: AsyncEngine) -> None:
    """Fail unless the pool connects as ``ibex_runtime``, not owner, not superuser.

    Runs once when the pool is first checked at startup, never per request, and
    never echoes the DSN.
    """
    violation = _login_violation(await _read_login_facts(engine))
    if violation is not None:
        raise CapabilityLoginError(violation)


__all__ = [
    "CAPABILITY_LOGIN",
    "OWNER_LOGIN",
    "CapabilityLoginError",
    "assert_capability_login",
]
