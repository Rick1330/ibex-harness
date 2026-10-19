"""Database helpers: engine factory guards and RLS org-GUC binding."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any, Self

import pytest

from app.config import Settings
from app.db import create_engine, session_with_org
from tests.fixtures import ORG


class _FakeBegin:
    async def __aenter__(self) -> None:
        return None

    async def __aexit__(self, *_exc: object) -> bool:
        return False


class _FakeSession:
    def __init__(self) -> None:
        self.executed: list[tuple[str, Mapping[str, Any] | None]] = []
        self.rollbacks = 0

    async def __aenter__(self) -> Self:
        return self

    async def __aexit__(self, *_exc: object) -> bool:
        return False

    def begin(self) -> _FakeBegin:
        return _FakeBegin()

    async def execute(self, stmt: Any, params: Mapping[str, Any] | None = None) -> None:
        self.executed.append((str(stmt), params))

    async def rollback(self) -> None:
        self.rollbacks += 1


def test_create_engine_requires_url() -> None:
    with pytest.raises(RuntimeError, match="DATABASE_URL is required"):
        create_engine(Settings(enabled=False))


@pytest.mark.asyncio
async def test_create_engine_builds_asyncpg_engine() -> None:
    engine = create_engine(
        Settings(
            enabled=True,
            database_url="postgresql+asyncpg://ibex_app:ibex_app@127.0.0.1:5432/ibex",
        )
    )
    assert engine.url.drivername.startswith("postgresql+asyncpg")
    await engine.dispose()


@pytest.mark.asyncio
async def test_session_with_org_binds_role_service_and_org_guc() -> None:
    session = _FakeSession()

    def factory() -> _FakeSession:
        return session

    async with session_with_org(factory, str(ORG)) as live:  # type: ignore[arg-type]
        assert live is session

    statements = [sql for sql, _ in session.executed]
    assert any("SET LOCAL ROLE ibex_app" in sql for sql in statements)
    assert any("app.is_service_account" in sql for sql in statements)
    org_stmt = next(
        (params for sql, params in session.executed if "app.current_org_id" in sql), None
    )
    assert org_stmt == {"org_id": str(ORG)}
