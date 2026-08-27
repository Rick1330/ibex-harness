"""Unit tests for dedup persist helpers (mocked session factory)."""

from __future__ import annotations

from contextlib import asynccontextmanager
from types import SimpleNamespace
from uuid import uuid4

import pytest

from app.dedup.persist import (
    ExactHashLookup,
    RetrievalBump,
    find_active_by_content_hash,
    increment_retrieval_count,
)


class _FakeResult:
    def __init__(self, row: object | None) -> None:
        self._row = row

    def one_or_none(self) -> object | None:
        return self._row


class _FakeSession:
    def __init__(self, rows: list[object | None]) -> None:
        self._rows = list(rows)
        self.executed: list[tuple[object, object | None]] = []

    async def execute(self, statement: object, params: object | None = None) -> _FakeResult:
        self.executed.append((statement, params))
        if self._rows:
            return _FakeResult(self._rows.pop(0))
        return _FakeResult(None)

    @asynccontextmanager
    async def begin(self):
        yield self


def _factory_for(session: _FakeSession):
    @asynccontextmanager
    async def _factory():
        yield session

    return _factory


@pytest.mark.asyncio
async def test_find_active_by_content_hash_miss() -> None:
    # set_config x2 + SELECT → three executes; only SELECT returns a row payload.
    session = _FakeSession([None, None, None])
    found = await find_active_by_content_hash(
        _factory_for(session),  # type: ignore[arg-type]
        ExactHashLookup(org_id=uuid4(), agent_id=uuid4(), content_hash="abc"),
    )
    assert found is None
    assert len(session.executed) == 3


@pytest.mark.asyncio
async def test_find_active_by_content_hash_hit() -> None:
    memory_id = uuid4()
    session = _FakeSession([None, None, SimpleNamespace(id=str(memory_id))])
    found = await find_active_by_content_hash(
        _factory_for(session),  # type: ignore[arg-type]
        ExactHashLookup(org_id=uuid4(), agent_id=uuid4(), content_hash="abc"),
    )
    assert found == memory_id


@pytest.mark.asyncio
async def test_increment_retrieval_count_success() -> None:
    session = _FakeSession([None, None, SimpleNamespace(retrieval_count=4)])
    count = await increment_retrieval_count(
        _factory_for(session),  # type: ignore[arg-type]
        RetrievalBump(org_id=uuid4(), memory_id=uuid4()),
    )
    assert count == 4


@pytest.mark.asyncio
async def test_increment_retrieval_count_missing_row() -> None:
    session = _FakeSession([None, None, None])
    with pytest.raises(RuntimeError, match="expected 1 row"):
        await increment_retrieval_count(
            _factory_for(session),  # type: ignore[arg-type]
            RetrievalBump(org_id=uuid4(), memory_id=uuid4()),
        )
