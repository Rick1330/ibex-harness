"""Unit tests for db engine/session helpers."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import Settings
from app.db import create_engine, create_session_factory, session_with_org


def test_create_engine_paths() -> None:
    with pytest.raises(RuntimeError):
        create_engine(Settings(database_url=None))
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
    assert session.execute.await_count == 1


@pytest.mark.asyncio
async def test_session_with_org_rolls_back_on_error() -> None:
    factory, session = _mock_org_session(execute_side_effect=RuntimeError("db"))
    with pytest.raises(RuntimeError):
        async with session_with_org(factory, str(uuid4())):
            pass
    session.rollback.assert_awaited()
