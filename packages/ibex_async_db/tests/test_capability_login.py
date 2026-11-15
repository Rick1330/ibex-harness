"""Unit tests for the shared capability-login startup assertion.

The assertion runs against a stubbed connection: no database is required. The
live behaviour under the real capability login is covered by each service's
integration suite. The five-case matrix lives here once; each service keeps a
small test proving its wrapper passes the right expected login.
"""

from __future__ import annotations

from typing import Self

import pytest

from ibex_async_db.capability_login import CapabilityLoginError, assert_capability_login

_RUNTIME = "ibex_runtime"
_WORKER = "ibex_worker"
_EXPECTED_LOGINS = pytest.mark.parametrize("expected_login", [_RUNTIME, _WORKER])


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


async def _run(
    row: tuple[object, ...], expected_login: str, service_label: str = "svc"
) -> None:
    """Run the assertion against a stub engine answering with *row*."""
    await assert_capability_login(
        _StubEngine(row),  # type: ignore[arg-type]
        expected_login=expected_login,
        service_label=service_label,
    )


@pytest.mark.asyncio
@_EXPECTED_LOGINS
async def test_assert_capability_login_accepts_the_expected_login(
    expected_login: str,
) -> None:
    await _run(_login_row(expected_login, expected_login), expected_login)


@pytest.mark.asyncio
@_EXPECTED_LOGINS
async def test_assert_capability_login_rejects_the_owner_login(expected_login: str) -> None:
    row = _login_row("ibex", "ibex", current_super=True, session_super=True)
    with pytest.raises(CapabilityLoginError, match="the owner login"):
        await _run(row, expected_login)


@pytest.mark.asyncio
@_EXPECTED_LOGINS
async def test_assert_capability_login_rejects_an_owner_session_behind_a_role_switch(
    expected_login: str,
) -> None:
    """``session_user`` is the login even after ``SET ROLE``."""
    with pytest.raises(CapabilityLoginError, match="the owner login"):
        await _run(_login_row(expected_login, "ibex"), expected_login)


@pytest.mark.asyncio
@_EXPECTED_LOGINS
async def test_assert_capability_login_rejects_a_superuser(expected_login: str) -> None:
    row = _login_row(expected_login, expected_login, current_super=True)
    with pytest.raises(CapabilityLoginError, match="is a superuser"):
        await _run(row, expected_login)


@pytest.mark.asyncio
@_EXPECTED_LOGINS
async def test_assert_capability_login_rejects_a_wrong_capability_login(
    expected_login: str,
) -> None:
    with pytest.raises(
        CapabilityLoginError,
        match=f"want the {expected_login!r} capability login",
    ):
        await _run(_login_row("ibex_app", "ibex_app"), expected_login)


@pytest.mark.asyncio
async def test_error_message_names_the_service_label() -> None:
    """The label tells an operator which process refused to boot."""
    with pytest.raises(CapabilityLoginError, match="^worker:"):
        await _run(_login_row("ibex_app", "ibex_app"), _WORKER, service_label="worker")
