"""Failure path of the lineage repository: a database error is not "not found".

A swallowed ``SQLAlchemyError`` would make `GET .../lineage` answer 404 during a
database outage, which is both the wrong status and an existence answer. The
repository must propagate so the router can map it to 503.
"""

from __future__ import annotations

from typing import Any, Self
from uuid import uuid4

import pytest
from sqlalchemy.exc import SQLAlchemyError

from app.read.lineage import LineageQuery, MemoryLineageRepository


class _Result:
    def __init__(self, rows: list[dict[str, Any]]) -> None:
        self._rows = rows

    def mappings(self) -> _Result:
        return self

    def first(self) -> dict[str, Any] | None:
        return self._rows[0] if self._rows else None

    def all(self) -> list[dict[str, Any]]:
        return list(self._rows)


class _FailingSession:
    """Answers the root lookup, then fails on the requested statement."""

    def __init__(self, *, fail_on: str, root: dict[str, Any] | None) -> None:
        self._fail_on = fail_on
        self._root = root

    async def __aenter__(self) -> Self:
        return self

    async def __aexit__(self, *_exc: object) -> bool:
        return False

    def begin(self) -> Self:
        return self

    async def execute(self, statement: object, params: object = None) -> _Result:
        sql = str(statement)
        if "set_config" in sql:
            return _Result([])
        if self._fail_on in sql:
            raise SQLAlchemyError("connection lost")
        if "resolve_supersession_tip" in sql:
            return _Result([self._root] if self._root is not None else [])
        return _Result([])


class _Factory:
    def __init__(self, session: _FailingSession) -> None:
        self._session = session

    def __call__(self) -> _FailingSession:
        return self._session


def _root_row() -> dict[str, Any]:
    memory_id = uuid4()
    return {"id": memory_id, "status": "active", "tombstoned": False, "tip": memory_id}


def _query() -> LineageQuery:
    return LineageQuery(org_id=uuid4(), memory_id=uuid4(), agent_id=None, max_depth=3)


@pytest.mark.asyncio
async def test_root_query_failure_propagates() -> None:
    repo = MemoryLineageRepository(  # type: ignore[arg-type]
        _Factory(_FailingSession(fail_on="resolve_supersession_tip", root=None))
    )

    with pytest.raises(SQLAlchemyError):
        await repo.get_lineage(_query())


@pytest.mark.asyncio
async def test_traversal_query_failure_propagates() -> None:
    repo = MemoryLineageRepository(  # type: ignore[arg-type]
        _Factory(_FailingSession(fail_on="WITH RECURSIVE walk", root=_root_row()))
    )

    with pytest.raises(SQLAlchemyError):
        await repo.get_lineage(_query())
