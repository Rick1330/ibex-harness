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

    async def execute(self, statement: object, params: object | None = None) -> _FakeResult:
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
        CandidateLoad(
            org_id=uuid4(),
            memory_ids=(),
            search_mode=SearchMode.HISTORICAL_CONFLICT_CANDIDATES,
        ),
    )
    assert loaded == []
    assert session.executed == []


@pytest.mark.asyncio
async def test_load_candidate_memories_rejects_user_retrieval_mode() -> None:
    session = _FakeSession([])
    candidate_load = CandidateLoad(
        org_id=uuid4(),
        memory_ids=(),
        search_mode=SearchMode.USER_RETRIEVAL,
    )
    with pytest.raises(ValueError, match="historical conflict-candidate mode"):
        await load_candidate_memories(_factory_for(session), candidate_load)  # type: ignore[arg-type]
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
    session = _FakeSession([_FakeResult(), _FakeResult(), _FakeResult(rows=[row])])
    loaded = await load_candidate_memories(
        _factory_for(session),  # type: ignore[arg-type]
        CandidateLoad(
            org_id=uuid4(),
            memory_ids=(mid, missing),
            search_mode=SearchMode.HISTORICAL_CONFLICT_CANDIDATES,
        ),
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
    session = _FakeSession([_FakeResult(), _FakeResult(), _FakeResult(rows=[row])])
    loaded = await load_candidate_memories(
        _factory_for(session),  # type: ignore[arg-type]
        CandidateLoad(
            org_id=uuid4(),
            memory_ids=(mid,),
            search_mode=SearchMode.HISTORICAL_CONFLICT_CANDIDATES,
        ),
    )
    assert loaded[0].interval.valid_until == vu


@pytest.mark.asyncio
async def test_apply_supersession_success_records_status_and_link() -> None:
    org_id = uuid4()
    new_memory_id = uuid4()
    target_memory_id = uuid4()
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
            org_id=org_id,
            new_memory_id=new_memory_id,
            target_memory_id=target_memory_id,
            closed_at=datetime(2026, 6, 1, tzinfo=UTC),
        ),
    )
    assert len(session.executed) == 4
    update_sql = str(session.executed[2][0])
    update_params = session.executed[2][1]
    assert "LEAST" in update_sql
    assert "SET status = 'superseded'" in update_sql
    assert "superseded_by = :new_id" in update_sql
    assert isinstance(update_params, dict)
    assert update_params["org_id"] == str(org_id)
    assert update_params["target_id"] == str(target_memory_id)
    assert update_params["new_id"] == str(new_memory_id)

    relationship_sql = str(session.executed[3][0])
    relationship_params = session.executed[3][1]
    assert "'supersedes'" in relationship_sql
    assert isinstance(relationship_params, dict)
    assert relationship_params["org_id"] == str(org_id)
    assert relationship_params["source_id"] == str(new_memory_id)
    assert relationship_params["target_id"] == str(target_memory_id)


@pytest.mark.asyncio
async def test_apply_supersession_sql_uses_least_coalesce_valid_until() -> None:
    """SQL-shape coverage: supersession UPDATE uses LEAST/COALESCE on valid_until."""
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
    session = _FakeSession([_FakeResult(), _FakeResult(), _FakeResult(rowcount=0)])
    factory = _factory_for(session)  # type: ignore[arg-type]
    apply = SupersedeApply(
        org_id=uuid4(),
        new_memory_id=uuid4(),
        target_memory_id=uuid4(),
    )
    with pytest.raises(RuntimeError, match="expected 1 row"):
        await apply_supersession(factory, apply)


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


from app.vectorstore.base import SearchMode
