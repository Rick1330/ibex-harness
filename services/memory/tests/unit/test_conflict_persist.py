"""Unit tests for conflict persist helpers (mocked session factory)."""

from __future__ import annotations

from contextlib import asynccontextmanager
from datetime import UTC, datetime
from types import SimpleNamespace
from uuid import uuid4

import pytest

from app.conflict.persist import (
    CandidateLoad,
    RelationshipInsert,
    apply_supersession,
    insert_relationship,
    load_candidate_memories,
)
from app.conflict.types import SupersedeApply


class _FakeResult:
    def __init__(
        self,
        *,
        rows: list[object] | None = None,
        rowcount: int = 0,
    ) -> None:
        self._rows = list(rows or [])
        self.rowcount = rowcount

    def all(self) -> list[object]:
        return self._rows


class _FakeSession:
    def __init__(self, results: list[_FakeResult]) -> None:
        self._results = list(results)
        self.executed: list[tuple[object, object | None]] = []

    async def execute(
        self, statement: object, params: object | None = None
    ) -> _FakeResult:
        self.executed.append((statement, params))
        if self._results:
            return self._results.pop(0)
        return _FakeResult()

    @asynccontextmanager
    async def begin(self):
        yield self


def _factory_for(session: _FakeSession):
    @asynccontextmanager
    async def _factory():
        yield session

    return _factory


@pytest.mark.asyncio
async def test_load_candidate_memories_empty_ids() -> None:
    session = _FakeSession([])
    loaded = await load_candidate_memories(
        _factory_for(session),  # type: ignore[arg-type]
        CandidateLoad(org_id=uuid4(), memory_ids=()),
    )
    assert loaded == []
    assert session.executed == []


@pytest.mark.asyncio
async def test_load_candidate_memories_maps_rows() -> None:
    mid = uuid4()
    missing = uuid4()
    vf = datetime(2026, 3, 1)  # noqa: DTZ001 — intentional naive row from DB
    row = SimpleNamespace(
        id=str(mid),
        content="User prefers Python",
        valid_from=vf,
        valid_until=None,
        confidence=0.9,
    )
    # set_config x2 + SELECT
    session = _FakeSession(
        [_FakeResult(), _FakeResult(), _FakeResult(rows=[row])]
    )
    loaded = await load_candidate_memories(
        _factory_for(session),  # type: ignore[arg-type]
        CandidateLoad(org_id=uuid4(), memory_ids=(mid, missing)),
    )
    assert len(loaded) == 1
    assert loaded[0].memory_id == mid
    assert loaded[0].interval.valid_from.tzinfo is not None
    assert loaded[0].interval.valid_until is None
    assert loaded[0].confidence == 0.9


@pytest.mark.asyncio
async def test_load_candidate_aware_until() -> None:
    mid = uuid4()
    vf = datetime(2026, 3, 1, tzinfo=UTC)
    vu = datetime(2026, 6, 1, tzinfo=UTC)
    row = SimpleNamespace(
        id=str(mid),
        content="x",
        valid_from=vf,
        valid_until=vu,
        confidence=0.8,
    )
    session = _FakeSession(
        [_FakeResult(), _FakeResult(), _FakeResult(rows=[row])]
    )
    loaded = await load_candidate_memories(
        _factory_for(session),  # type: ignore[arg-type]
        CandidateLoad(org_id=uuid4(), memory_ids=(mid,)),
    )
    assert loaded[0].interval.valid_until == vu


@pytest.mark.asyncio
async def test_apply_supersession_success() -> None:
    session = _FakeSession(
        [
            _FakeResult(),
            _FakeResult(),
            _FakeResult(rowcount=1),
            _FakeResult(),
        ]
    )
    await apply_supersession(
        _factory_for(session),  # type: ignore[arg-type]
        SupersedeApply(
            org_id=uuid4(),
            new_memory_id=uuid4(),
            target_memory_id=uuid4(),
            closed_at=datetime(2026, 6, 1, tzinfo=UTC),
        ),
    )
    assert len(session.executed) == 4
    update_sql = str(session.executed[2][0])
    assert "LEAST" in update_sql


@pytest.mark.asyncio
async def test_apply_supersession_preserves_earlier_valid_until() -> None:
    """Regression: later valid_until is closed; earlier valid_until is kept."""
    session = _FakeSession(
        [
            _FakeResult(),
            _FakeResult(),
            _FakeResult(rowcount=1),
            _FakeResult(),
        ]
    )
    closed_at = datetime(2026, 6, 1, tzinfo=UTC)
    await apply_supersession(
        _factory_for(session),  # type: ignore[arg-type]
        SupersedeApply(
            org_id=uuid4(),
            new_memory_id=uuid4(),
            target_memory_id=uuid4(),
            closed_at=closed_at,
        ),
    )
    update_sql = str(session.executed[2][0])
    assert "LEAST(COALESCE(valid_until" in update_sql.replace("\n", " ")


@pytest.mark.asyncio
async def test_apply_supersession_missing_row() -> None:
    session = _FakeSession(
        [_FakeResult(), _FakeResult(), _FakeResult(rowcount=0)]
    )
    with pytest.raises(RuntimeError, match="expected 1 row"):
        await apply_supersession(
            _factory_for(session),  # type: ignore[arg-type]
            SupersedeApply(
                org_id=uuid4(),
                new_memory_id=uuid4(),
                target_memory_id=uuid4(),
            ),
        )


@pytest.mark.asyncio
async def test_insert_relationship() -> None:
    session = _FakeSession([_FakeResult(), _FakeResult(), _FakeResult()])
    await insert_relationship(
        _factory_for(session),  # type: ignore[arg-type]
        RelationshipInsert(
            org_id=uuid4(),
            source_memory_id=uuid4(),
            target_memory_id=uuid4(),
            relationship_type="contradicts",
            resolution_notes="fixture",
        ),
    )
    assert len(session.executed) == 3
