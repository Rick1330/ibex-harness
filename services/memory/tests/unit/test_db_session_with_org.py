"""Unit tests for the session helper that pins the tenant role."""

from __future__ import annotations

from contextlib import asynccontextmanager
from typing import Self
from uuid import uuid4

import pytest

from app.db import session_with_org


class _FakeTransaction:
    """Minimal async context manager for ``session.begin()``."""
    async def __aenter__(self) -> Self:
        return self

    async def __aexit__(self, *exc: object) -> bool:
        return False


class _FakeSession:
    """Records the statements a transaction issues."""
    def __init__(self) -> None:
        self.statements: list[str] = []
        self.rolled_back = False

    def begin(self) -> _FakeTransaction:
        return _FakeTransaction()

    async def execute(self, statement: object, params: object = None) -> None:
        del params
        self.statements.append(str(statement))

    async def rollback(self) -> None:
        self.rolled_back = True


def _factory_for(session: _FakeSession):
    """Return a session factory that always yields ``session``."""
    @asynccontextmanager
    async def _factory():
        yield session

    return _factory


@pytest.mark.asyncio
async def test_session_with_org_pins_the_tenant_role_and_org() -> None:
    """The helper clears the bypass, pins ibex_app, and sets the org GUC."""
    session = _FakeSession()

    async with session_with_org(_factory_for(session), str(uuid4())) as opened:
        assert opened is session

    joined = " ".join(session.statements)
    assert "SET LOCAL ROLE ibex_app" in joined
    assert "app.current_org_id" in joined
    assert "app.is_service_account" in joined


class _FailingSession(_FakeSession):
    """Session whose every statement fails, to exercise the rollback path."""

    async def execute(self, statement: object, params: object = None) -> None:
        del statement, params
        raise RuntimeError("database unavailable")


async def _open(factory) -> None:
    """Enter and leave the helper so a failure surfaces from the pin itself."""
    async with session_with_org(factory, str(uuid4())):
        pass


@pytest.mark.asyncio
async def test_session_with_org_rolls_back_when_pinning_fails() -> None:
    """A failing pin rolls the transaction back and propagates."""
    session = _FailingSession()
    factory = _factory_for(session)
    with pytest.raises(RuntimeError, match="database unavailable"):
        await _open(factory)
    assert session.rolled_back
