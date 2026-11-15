"""Unit tests for db engine/session helpers."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch
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


@pytest.mark.asyncio
async def test_assert_capability_login_uses_the_runtime_login() -> None:
    """The wrapper supplies the API's expected login and label to the shared check.

    The check's behaviour is covered once in ``ibex_async_db``; this proves the
    API wrapper cannot drift from the expected login.
    """
    with patch("app.db._assert_capability_login", new=AsyncMock()) as shared:
        await assert_capability_login(MagicMock())  # type: ignore[arg-type]
    _, kwargs = shared.await_args
    assert kwargs == {"expected_login": CAPABILITY_LOGIN, "service_label": "api"}
    assert CAPABILITY_LOGIN == "ibex_runtime"


def test_capability_login_error_is_the_shared_one() -> None:
    """Lifespan tests catch this class; it must be the shared exception type."""
    from ibex_async_db.capability_login import CapabilityLoginError as Shared

    assert CapabilityLoginError is Shared
