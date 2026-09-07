"""Unit tests for feedback persist path (mocked session factory)."""

from __future__ import annotations

from contextlib import asynccontextmanager
from types import SimpleNamespace
from uuid import uuid4

import pytest

from app.exceptions import MemoryNotFoundError, ValidationError
from app.feedback.models import ApplyFeedbackCommand, FeedbackKind
from app.feedback.persist import (
    apply_feedback_session,
    parse_feedback_kind,
    require_agent_id,
)
from app.feedback.service import MemoryFeedbackService
from tests.unit.memory_test_support import mapping_row


class _FakeResult:
    def __init__(self, row: object | None) -> None:
        self._row = row

    def one_or_none(self) -> object | None:
        return self._row

    def one(self) -> object:
        if self._row is None:
            raise RuntimeError("no row")
        return self._row


class _FakeSession:
    def __init__(self, rows: list[object | None]) -> None:
        self._rows = list(rows)
        self.executed: list[object] = []

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


def _command(**overrides: object) -> ApplyFeedbackCommand:
    base = {
        "org_id": uuid4(),
        "agent_id": uuid4(),
        "memory_id": uuid4(),
        "feedback": FeedbackKind.POSITIVE,
    }
    base.update(overrides)
    return ApplyFeedbackCommand(**base)  # type: ignore[arg-type]


@pytest.mark.asyncio
async def test_apply_feedback_session_happy_path() -> None:
    org_id = uuid4()
    agent_id = uuid4()
    memory_id = uuid4()
    load_row = mapping_row(id=memory_id, org_id=org_id, agent_id=agent_id)
    updated = mapping_row(
        id=memory_id, org_id=org_id, agent_id=agent_id, usefulness_score=0.67
    )
    # set_config x2 + load + upsert + counts + update returning
    session = _FakeSession(
        [
            None,
            None,
            load_row,
            None,
            SimpleNamespace(positive=1, negative=0),
            updated,
        ]
    )
    result, memory = await apply_feedback_session(
        _factory_for(session),  # type: ignore[arg-type]
        _command(org_id=org_id, agent_id=agent_id, memory_id=memory_id),
    )
    assert result.total_positive_feedback == 1
    assert result.new_usefulness_score == pytest.approx(0.67)
    assert memory.usefulness_score == pytest.approx(0.67)
    assert len(session.executed) == 6


@pytest.mark.asyncio
async def test_apply_feedback_session_missing_memory() -> None:
    session = _FakeSession([None, None, None])
    with pytest.raises(MemoryNotFoundError):
        await apply_feedback_session(
            _factory_for(session),  # type: ignore[arg-type]
            _command(),
        )


@pytest.mark.asyncio
async def test_apply_feedback_session_update_missing_row() -> None:
    org_id = uuid4()
    agent_id = uuid4()
    memory_id = uuid4()
    load_row = mapping_row(id=memory_id, org_id=org_id, agent_id=agent_id)
    session = _FakeSession(
        [
            None,
            None,
            load_row,
            None,
            SimpleNamespace(positive=0, negative=0),
            None,
        ]
    )
    with pytest.raises(MemoryNotFoundError):
        await apply_feedback_session(
            _factory_for(session),  # type: ignore[arg-type]
            _command(org_id=org_id, agent_id=agent_id, memory_id=memory_id),
        )


@pytest.mark.asyncio
async def test_service_apply_refreshes_hot_cache() -> None:
    org_id = uuid4()
    agent_id = uuid4()
    memory_id = uuid4()
    load_row = mapping_row(id=memory_id, org_id=org_id, agent_id=agent_id)
    updated = mapping_row(
        id=memory_id, org_id=org_id, agent_id=agent_id, usefulness_score=0.67
    )
    session = _FakeSession(
        [
            None,
            None,
            load_row,
            None,
            SimpleNamespace(positive=1, negative=0),
            updated,
        ]
    )
    cache = type("C", (), {})()
    calls: list[object] = []

    async def refresh_hot(memory: object) -> None:
        calls.append(memory)

    cache.refresh_hot = refresh_hot  # type: ignore[attr-defined]
    service = MemoryFeedbackService(
        _factory_for(session),  # type: ignore[arg-type]
        cache_writer=cache,  # type: ignore[arg-type]
    )
    result = await service.apply(
        _command(org_id=org_id, agent_id=agent_id, memory_id=memory_id)
    )
    assert result.new_usefulness_score == pytest.approx(0.67)
    assert len(calls) == 1


def test_require_agent_id_and_parse_kind() -> None:
    agent = uuid4()
    assert require_agent_id(agent) == agent
    with pytest.raises(ValidationError):
        require_agent_id(None)
    assert parse_feedback_kind("negative") is FeedbackKind.NEGATIVE
    with pytest.raises(ValidationError):
        parse_feedback_kind("nope")
