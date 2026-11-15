"""Startup assertion that the memory pool connects as its capability login.

The v1 profile connects memory on ``ibex_runtime``. A wrong *password* fails
loudly at connect; a wrong *login* starts silently and quietly re-enables the
RLS bypass the tenancy claim rests on, because the owner login is a superuser
and ``FORCE ROW LEVEL SECURITY`` does not cover superusers. This module makes
that failure a startup failure.

The check itself lives in ``ibex_async_db.capability_login`` so it cannot
diverge from the API and worker copies; this module is the thin wrapper that
supplies memory's expected login and label.
"""

from __future__ import annotations

from ibex_async_db.capability_login import (
    OWNER_LOGIN,
    CapabilityLoginError,
)
from ibex_async_db.capability_login import (
    assert_capability_login as _assert_capability_login,
)
from sqlalchemy.ext.asyncio import AsyncEngine

# The capability login the memory service must connect as. A module constant,
# not a setting: the DSN already names the login, and a second configurable
# source would let the assertion below be reconfigured to match a mistake.
CAPABILITY_LOGIN = "ibex_runtime"


async def assert_capability_login(engine: AsyncEngine) -> None:
    """Fail unless the pool connects as ``ibex_runtime``, not owner, not superuser.

    Runs once when the pool is first checked at startup, never per request, and
    never echoes the DSN.
    """
    await _assert_capability_login(
        engine, expected_login=CAPABILITY_LOGIN, service_label="memory"
    )


__all__ = [
    "CAPABILITY_LOGIN",
    "OWNER_LOGIN",
    "CapabilityLoginError",
    "assert_capability_login",
]
