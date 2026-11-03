"""Repository SQL shape and row mapping (no database; fake session)."""

from __future__ import annotations

from collections.abc import Mapping
from datetime import UTC, datetime
from typing import Any

import pytest
from mcp_gateway import NotFoundError

from app import repositories
from tests.fixtures import AGENT, ORG, RUN_ID, SESSION_ID

_NOW = datetime(2026, 10, 19, 12, 0, tzinfo=UTC)


class _Mappings:
    def __init__(self, rows: list[dict[str, Any]]) -> None:
        self._rows = rows

    def first(self) -> dict[str, Any] | None:
        return self._rows[0] if self._rows else None

    def all(self) -> list[dict[str, Any]]:
        return list(self._rows)


class _Result:
    def __init__(self, rows: list[dict[str, Any]]) -> None:
        self._rows = rows

    def mappings(self) -> _Mappings:
        return _Mappings(self._rows)


class FakeSession:
    def __init__(self, rows: list[dict[str, Any]] | None = None) -> None:
        self._rows = rows or []
        self.calls: list[tuple[str, Mapping[str, Any] | None]] = []

    async def execute(self, stmt: Any, params: Mapping[str, Any] | None = None) -> _Result:
        self.calls.append((str(stmt), params))
        return _Result(self._rows)


def _session_row() -> dict[str, Any]:
    return {
        "id": SESSION_ID,
        "status": "active",
        "model": "gpt-4o-mini",
        "provider": "openai",
        "agent_id": AGENT,
        "turn_count": 2,
        "total_input_tokens": 10,
        "total_output_tokens": 5,
        "created_at": _NOW,
        "updated_at": _NOW,
        "completed_at": None,
    }


def _run_row() -> dict[str, Any]:
    return {
        "id": RUN_ID,
        "trace_id": "trace-1",
        "request_id": "req-1",
        "status": "ok",
        "error_code": None,
        "completeness": "complete",
        "capture_mode": "metadata",
        "sample_decision": "sampled",
        "schema_version": "evidence.v1",
        "agent_id": AGENT,
        "session_id": SESSION_ID,
        "started_at": _NOW,
        "ended_at": None,
    }


def _budget_row() -> dict[str, Any]:
    return {
        "id": SESSION_ID,
        "period_start": _NOW,
        "period_end": _NOW,
        "cap_cents": 5000,
        "spent_cents_cached": 120,
        "enforcement_mode": "alert_only",
    }


@pytest.mark.asyncio
async def test_get_session_maps_row_and_filters_org() -> None:
    session = FakeSession([_session_row()])
    result = await repositories.get_session(session, org_id=ORG, session_id=SESSION_ID)  # type: ignore[arg-type]
    assert result["session_id"] == str(SESSION_ID)
    assert result["created_at"] == _NOW.isoformat()
    assert result["completed_at"] is None
    sql, params = session.calls[0]
    assert "org_id = :org_id" in sql
    assert "deleted_at IS NULL" in sql
    assert params == {"org_id": str(ORG), "session_id": str(SESSION_ID)}


@pytest.mark.asyncio
async def test_get_session_missing_raises_not_found() -> None:
    session = FakeSession([])
    with pytest.raises(NotFoundError):
        await repositories.get_session(session, org_id=ORG, session_id=SESSION_ID)  # type: ignore[arg-type]


@pytest.mark.asyncio
async def test_get_run_maps_row_and_missing() -> None:
    found = FakeSession([_run_row()])
    result = await repositories.get_run(found, org_id=ORG, run_id=RUN_ID)  # type: ignore[arg-type]
    assert result["run_id"] == str(RUN_ID)
    assert result["trace_id"] == "trace-1"

    missing = FakeSession([])
    with pytest.raises(NotFoundError):
        await repositories.get_run(missing, org_id=ORG, run_id=RUN_ID)  # type: ignore[arg-type]


@pytest.mark.asyncio
async def test_query_evidence_applies_filters_and_truncation() -> None:
    session = FakeSession([_run_row(), _run_row()])
    result = await repositories.query_evidence(
        session,  # type: ignore[arg-type]
        org_id=ORG,
        filters=repositories.EvidenceFilters(
            trace_id="4bf92f3577b34da6a3ce929d0e0e4736",
            session_id=SESSION_ID,
            request_id="req-1",
            error_code="E1",
            status="error",
        ),
        limit=1,
    )
    assert result["count"] == 1
    assert result["truncated"] is True
    sql, params = session.calls[0]
    assert "CAST(:trace_id AS text) IS NULL" in sql
    assert "trace_id = CAST(:trace_id AS text)" in sql
    assert "CAST(:session_id AS uuid) IS NULL" in sql
    assert "CAST(:request_id AS text) IS NULL" in sql
    assert "CAST(:error_code AS text) IS NULL" in sql
    assert "CAST(:status AS text) = 'error' AND status <> 'ok'" in sql
    assert params["limit"] == 2
    assert params["trace_id"] == "4bf92f3577b34da6a3ce929d0e0e4736"
    assert params["session_id"] == str(SESSION_ID)
    assert params["status"] == "error"


@pytest.mark.asyncio
async def test_query_evidence_ok_status_and_no_truncation() -> None:
    session = FakeSession([_run_row()])
    result = await repositories.query_evidence(
        session,  # type: ignore[arg-type]
        org_id=ORG,
        filters=repositories.EvidenceFilters(status="ok"),
        limit=10,
    )
    assert result["count"] == 1
    assert result["truncated"] is False
    sql, params = session.calls[0]
    assert "CAST(:status AS text) = 'ok' AND status = 'ok'" in sql
    assert params["trace_id"] is None
    assert params["status"] == "ok"


@pytest.mark.asyncio
async def test_budget_active_only_adds_window() -> None:
    session = FakeSession([_budget_row()])
    result = await repositories.get_budget_periods(
        session,
        org_id=ORG,
        active_only=True,
        limit=5,  # type: ignore[arg-type]
    )
    assert result["periods"][0]["cap_cents"] == 5000
    assert result["periods"][0]["period_id"] == str(SESSION_ID)
    sql, params = session.calls[0]
    assert "NOT CAST(:active_only AS boolean)" in sql
    assert "period_start <= NOW() AND period_end > NOW()" in sql
    assert params["active_only"] is True


@pytest.mark.asyncio
async def test_budget_without_active_filter() -> None:
    session = FakeSession([])
    result = await repositories.get_budget_periods(
        session,
        org_id=ORG,
        active_only=False,
        limit=5,  # type: ignore[arg-type]
    )
    assert result == {"periods": [], "count": 0, "truncated": False}
    sql, params = session.calls[0]
    assert "NOT CAST(:active_only AS boolean)" in sql
    assert params["active_only"] is False
