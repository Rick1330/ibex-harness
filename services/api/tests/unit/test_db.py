"""Unit tests for db engine/session helpers."""

from __future__ import annotations

from typing import Self
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import Settings
from app.db import (
    CAPABILITY_LOGIN,
    CapabilityLoginError,
    assert_capability_login,
    create_engine,
    create_session_factory,
    session_with_org,
)


def test_create_engine_requires_database_url() -> None:
    with pytest.raises(RuntimeError):
        create_engine(Settings(database_url=None))


def test_create_engine_masks_bound_parameters() -> None:
    """A DBAPIError's text must never carry the statement's parameters."""
    engine = create_engine(
        Settings(database_url="postgresql+asyncpg://ibex:ibex@127.0.0.1:5432/ibex")
    )
    assert engine.sync_engine.hide_parameters is True


def test_create_engine_and_session_factory() -> None:
    settings = Settings(database_url="postgresql+asyncpg://ibex:ibex@127.0.0.1:5432/ibex")
    engine = create_engine(settings)
    factory = create_session_factory(engine)
    assert factory.class_ is AsyncSession


def _mock_org_session(*, execute_side_effect: object | None = None):
    session = MagicMock()
    session.execute = (
        AsyncMock(side_effect=execute_side_effect)
        if execute_side_effect is not None
        else AsyncMock()
    )
    begin_cm = MagicMock()
    begin_cm.__aenter__ = AsyncMock(return_value=None)
    begin_cm.__aexit__ = AsyncMock(return_value=None)
    session.begin = MagicMock(return_value=begin_cm)
    session.rollback = AsyncMock()
    factory = MagicMock()
    factory.return_value.__aenter__ = AsyncMock(return_value=session)
    factory.return_value.__aexit__ = AsyncMock(return_value=None)
    return factory, session


@pytest.mark.asyncio
async def test_session_with_org_sets_guc_via_mock() -> None:
    factory, session = _mock_org_session()
    async with session_with_org(factory, str(uuid4())) as yielded:
        assert yielded is session
    assert session.execute.await_count == 3


@pytest.mark.asyncio
async def test_session_with_org_rolls_back_on_error() -> None:
    factory, session = _mock_org_session(execute_side_effect=RuntimeError("db"))
    with pytest.raises(RuntimeError):
        async with session_with_org(factory, str(uuid4())):
            pass
    session.rollback.assert_awaited()


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
