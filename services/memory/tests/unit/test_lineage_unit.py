"""Unit tests for the bounded lineage traversal (milestone 5.B.1)."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Self
from uuid import UUID, uuid4

import pytest

from app.read.lineage import (
    _LINEAGE_SQL,
    MAX_LINEAGE_DEPTH,
    MAX_LINEAGE_EDGES,
    STATEMENT_TIMEOUT,
    LineageQuery,
    MemoryLineageRepository,
    _edges_from_rows,
    validate_lineage_query,
)


@dataclass(frozen=True, slots=True)
class _FakeResult:
    rows: list[dict[str, Any]]

    def mappings(self) -> _FakeResult:
        return self

    def first(self) -> dict[str, Any] | None:
        return self.rows[0] if self.rows else None

    def all(self) -> list[dict[str, Any]]:
        return list(self.rows)


class _FakeSession:
    """Routes the three statements the repository issues by their shape."""

    def __init__(self, root: dict[str, Any] | None, edges: list[dict[str, Any]]) -> None:
        self._root = root
        self._edges = edges
        self.calls: list[tuple[str, dict[str, Any] | None]] = []

    async def __aenter__(self) -> Self:
        return self

    async def __aexit__(self, *_exc: object) -> bool:
        return False

    def begin(self) -> _FakeSession:
        return self

    async def execute(self, statement: object, params: dict[str, Any] | None = None) -> _FakeResult:
        sql = str(statement)
        self.calls.append((sql, params))
        if "set_config" in sql:
            return _FakeResult([])
        if "resolve_supersession_tip" in sql:
            return _FakeResult([self._root] if self._root is not None else [])
        return _FakeResult(self._edges)


class _FakeFactory:
    def __init__(self, session: _FakeSession) -> None:
        self._session = session

    def __call__(self) -> _FakeSession:
        return self._session


def _root_row(memory_id: UUID, tip: UUID, *, status: str = "active") -> dict[str, Any]:
    return {"id": memory_id, "status": status, "tombstoned": False, "tip": tip}


def _edge_row(
    *,
    depth: int = 1,
    relationship_type: str = "supersedes",
) -> dict[str, Any]:
    return {
        "edge_id": uuid4(),
        "source_id": uuid4(),
        "target_id": uuid4(),
        "relationship_type": relationship_type,
        "confidence": 0.9,
        "depth": depth,
        "from_id": uuid4(),
        "other_id": uuid4(),
        "other_status": "superseded",
        "other_tombstoned": False,
    }


def _query(**overrides: Any) -> LineageQuery:
    base: dict[str, Any] = {
        "org_id": uuid4(),
        "memory_id": uuid4(),
        "agent_id": None,
        "max_depth": 3,
    }
    base.update(overrides)
    return LineageQuery(**base)


@pytest.mark.parametrize("depth", [0, MAX_LINEAGE_DEPTH + 1])
def test_validate_lineage_query_rejects_out_of_range_depth(depth: int) -> None:
    with pytest.raises(ValueError, match="max_depth"):
        validate_lineage_query(_query(max_depth=depth))


@pytest.mark.parametrize("depth", [1, 2, 3, 4, 5])
def test_validate_lineage_query_accepts_bounded_depth(depth: int) -> None:
    validate_lineage_query(_query(max_depth=depth))


def test_traversal_sql_carries_the_depth_cap() -> None:
    assert "w.depth < :max_depth" in _LINEAGE_SQL


def test_traversal_sql_filters_org_at_every_level() -> None:
    # Base term, edge join, next-node join, and the far-end join: a tenant
    # predicate at each level is the milestone's isolation requirement.
    assert _LINEAGE_SQL.count("org_id = :org_id") >= 4


def test_traversal_sql_breaks_cycles_on_the_path_array() -> None:
    assert "= ANY (w.path)" in _LINEAGE_SQL


async def test_get_lineage_returns_none_when_root_is_not_visible() -> None:
    session = _FakeSession(root=None, edges=[])
    repo = MemoryLineageRepository(_FakeFactory(session))  # type: ignore[arg-type]

    assert await repo.get_lineage(_query()) is None


async def test_get_lineage_maps_root_and_edges() -> None:
    memory_id, tip = uuid4(), uuid4()
    session = _FakeSession(
        root=_root_row(memory_id, tip, status="superseded"),
        edges=[_edge_row(depth=1), _edge_row(depth=2, relationship_type="contradicts")],
    )
    repo = MemoryLineageRepository(_FakeFactory(session))  # type: ignore[arg-type]

    result = await repo.get_lineage(_query(memory_id=memory_id))

    assert result is not None
    assert result.root.memory_id == memory_id
    assert result.root.status == "superseded"
    assert result.root.supersession_tip == tip
    assert [edge.depth for edge in result.edges] == [1, 2]
    assert result.edges[1].relationship_type == "contradicts"
    assert result.truncated is False
    assert result.max_depth == 3


async def test_get_lineage_marks_truncation_and_stops_at_the_cap() -> None:
    session = _FakeSession(
        root=_root_row(uuid4(), uuid4()),
        edges=[_edge_row() for _ in range(MAX_LINEAGE_EDGES + 1)],
    )
    repo = MemoryLineageRepository(_FakeFactory(session))  # type: ignore[arg-type]

    result = await repo.get_lineage(_query())

    assert result is not None
    assert len(result.edges) == MAX_LINEAGE_EDGES
    assert result.truncated is True


async def test_get_lineage_binds_the_agent_scope() -> None:
    agent_id = uuid4()
    session = _FakeSession(root=_root_row(uuid4(), uuid4()), edges=[])
    repo = MemoryLineageRepository(_FakeFactory(session))  # type: ignore[arg-type]

    await repo.get_lineage(_query(agent_id=agent_id))

    root_params = [
        params
        for sql, params in session.calls
        if "resolve_supersession_tip" in sql
    ]
    assert root_params[0]["agent_id"] == str(agent_id)


def test_edges_from_rows_drops_the_truncation_probe() -> None:
    rows = [_edge_row() for _ in range(MAX_LINEAGE_EDGES + 1)]

    edges = _edges_from_rows(rows)

    assert len(edges) == MAX_LINEAGE_EDGES
    assert all(isinstance(edge.confidence, float) for edge in edges)


def test_edge_row_is_typed_against_the_schema() -> None:
    row = _edge_row()
    edge = _edges_from_rows([row])[0]
    assert edge.other.status == "superseded"
    assert isinstance(edge.other.memory_id, UUID)
    assert edge.relationship_type == "supersedes"


async def test_get_lineage_bounds_the_walk_with_a_statement_timeout() -> None:
    # The traversal is bounded by a local statement timeout as well as by depth:
    # a dense graph must fail fast instead of holding a connection.
    session = _FakeSession(root=_root_row(uuid4(), uuid4()), edges=[])
    repo = MemoryLineageRepository(_FakeFactory(session))  # type: ignore[arg-type]

    await repo.get_lineage(_query())

    timeouts = [
        params for sql, params in session.calls if "statement_timeout" in sql
    ]
    assert timeouts == [{"timeout": STATEMENT_TIMEOUT}]
