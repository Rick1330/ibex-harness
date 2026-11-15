"""Unit tests for the memory startup capability-login assertion.

The assertion runs against a stubbed connection: no database is required. The
live behaviour under the real capability login is covered by the memory
integration suite.
"""

from __future__ import annotations

from typing import Self

import pytest

from app.capability_login import (
    CAPABILITY_LOGIN,
    CapabilityLoginError,
    assert_capability_login,
)


class _StubResult:
    """Double for a SQLAlchemy result carrying one login row."""

    def __init__(self, row: tuple[object, ...]) -> None:
        self._row = row

    def one(self) -> tuple[object, ...]:
        return self._row


class _StubConnection:
    """Async context-manager connection that answers with a fixed row."""

    def __init__(self, row: tuple[object, ...]) -> None:
        self._row = row

    async def __aenter__(self) -> Self:
        return self

    async def __aexit__(self, *exc: object) -> bool:
        return False

    async def execute(self, _statement: object) -> _StubResult:
        return _StubResult(self._row)


class _StubEngine:
    """Engine double whose pool reports a fixed login identity."""

    def __init__(self, row: tuple[object, ...]) -> None:
        self._row = row

    def connect(self) -> _StubConnection:
        return _StubConnection(self._row)

    async def dispose(self) -> None:
        return None


def _login_row(
    current: str,
    session: str,
    *,
    current_super: bool = False,
    session_super: bool = False,
) -> tuple[object, ...]:
    return (current, session, current_super, session_super)


@pytest.mark.asyncio
async def test_assert_capability_login_accepts_the_runtime_login() -> None:
    engine = _StubEngine(_login_row(CAPABILITY_LOGIN, CAPABILITY_LOGIN))
    await assert_capability_login(engine)  # type: ignore[arg-type]


@pytest.mark.asyncio
async def test_assert_capability_login_rejects_the_owner_login() -> None:
    engine = _StubEngine(_login_row("ibex", "ibex", current_super=True, session_super=True))
    with pytest.raises(CapabilityLoginError, match="the owner login"):
        await assert_capability_login(engine)  # type: ignore[arg-type]


@pytest.mark.asyncio
async def test_assert_capability_login_rejects_an_owner_session_behind_a_role_switch() -> None:
    """``session_user`` is the login even after ``SET ROLE``."""
    engine = _StubEngine(_login_row(CAPABILITY_LOGIN, "ibex"))
    with pytest.raises(CapabilityLoginError, match="the owner login"):
        await assert_capability_login(engine)  # type: ignore[arg-type]


@pytest.mark.asyncio
async def test_assert_capability_login_rejects_a_superuser() -> None:
    engine = _StubEngine(_login_row(CAPABILITY_LOGIN, CAPABILITY_LOGIN, current_super=True))
    with pytest.raises(CapabilityLoginError, match="is a superuser"):
        await assert_capability_login(engine)  # type: ignore[arg-type]


@pytest.mark.asyncio
async def test_assert_capability_login_rejects_a_wrong_capability_login() -> None:
    engine = _StubEngine(_login_row("ibex_app", "ibex_app"))
    with pytest.raises(CapabilityLoginError, match="want the 'ibex_runtime' capability login"):
        await assert_capability_login(engine)  # type: ignore[arg-type]
