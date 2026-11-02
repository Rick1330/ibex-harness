"""Unit tests for the metadata-only operator evidence summary service."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest

from app.schemas.operator_evidence import EvidenceRange
from app.services import operator_evidence as evidence_service
from app.services.operator_evidence import EvidenceSummaryArgs, window_for

NOW = datetime(2026, 11, 2, 12, 0, tzinfo=UTC)


class _MapResult:
    def __init__(self, rows: list[dict[str, object]] | None = None) -> None:
        self._rows = rows or []

    def mappings(self) -> _MapResult:
        return self

    def all(self) -> list[dict[str, object]]:
        return list(self._rows)


def _session(*results: list[dict[str, object]]) -> AsyncMock:
    session = AsyncMock()
    session.execute = AsyncMock(side_effect=[_MapResult(rows) for rows in results])
    return session


def _args(range_value: EvidenceRange = "24h") -> EvidenceSummaryArgs:
    return EvidenceSummaryArgs(org_id=uuid4(), range=range_value)


def _run_row(completeness: str, status: str, count: int, last: datetime | None) -> dict[str, object]:
    return {
        "completeness": completeness,
        "status": status,
        "row_count": count,
        "last_run_at": last,
    }


def _delivery_row(
    status: str,
    count: int,
    oldest_pending_at: datetime | None = None,
    last_delivered_at: datetime | None = None,
) -> dict[str, object]:
    return {
        "delivery_status": status,
        "row_count": count,
        "oldest_pending_at": oldest_pending_at,
        "last_delivered_at": last_delivered_at,
    }


@pytest.mark.asyncio
async def test_summary_projects_every_grouped_fact() -> None:
    last_run = NOW - timedelta(minutes=5)
    oldest_pending = NOW - timedelta(minutes=30)
    last_delivered = NOW - timedelta(minutes=2)
    session = _session(
        [
            _run_row("complete", "ok", 12, last_run),
            _run_row("complete", "error", 2, last_run),
            _run_row("partial", "ok", 3, last_run),
            _run_row("sampled", "ok", 1, last_run),
        ],
        [
            _delivery_row("delivered", 15, None, last_delivered),
            _delivery_row("pending", 2, oldest_pending),
            _delivery_row("poison", 1, oldest_pending),
        ],
        [{"mode": "metadata_only", "agent_id": None}],
        [{"created_at": NOW - timedelta(days=1)}],
    )

    summary = await evidence_service.get_evidence_summary(session, _args(), now=NOW)

    assert summary.schema_version == "operator.evidence.summary.v1"
    assert summary.range == "24h"
    assert summary.window_end == NOW
    assert summary.window_start == NOW - timedelta(hours=24)
    assert summary.runs_total == 18
    assert summary.capture_complete_runs == 14
    assert summary.completeness.complete == 14
    assert summary.completeness.partial == 3
    assert summary.completeness.sampled == 1
    # An error outcome is still a complete capture, so it does not lower the count.
    assert summary.statuses.ok == 16
    assert summary.statuses.error == 2
    assert summary.last_run_at == last_run
    assert summary.delivery.delivered == 15
    assert summary.delivery.pending == 2
    assert summary.delivery.poison == 1
    assert summary.oldest_pending_at == oldest_pending
    assert summary.last_delivered_at == last_delivered
    assert summary.capture_policy.mode == "metadata_only"
    assert summary.capture_policy.scope == "org"
    assert summary.capture_policy.agent_overrides == 0
    assert summary.legal_hold.active is True
    assert summary.legal_hold.since == NOW - timedelta(days=1)


@pytest.mark.asyncio
async def test_summary_is_empty_not_estimated_when_nothing_was_recorded() -> None:
    session = _session([], [], [], [])

    summary = await evidence_service.get_evidence_summary(session, _args("7d"), now=NOW)

    assert summary.runs_total == 0
    assert summary.capture_complete_runs == 0
    assert summary.completeness.complete == 0
    assert summary.last_run_at is None
    assert summary.delivery.delivered == 0
    assert summary.oldest_pending_at is None
    assert summary.last_delivered_at is None
    assert summary.capture_policy.mode is None
    assert summary.capture_policy.scope is None
    assert summary.legal_hold.active is False
    assert summary.legal_hold.since is None


@pytest.mark.asyncio
async def test_unknown_enum_values_are_ignored_rather_than_guessed() -> None:
    session = _session(
        [_run_row("teleported", "ok", 4, NOW), _run_row("complete", "maybe", 2, NOW)],
        [_delivery_row("exploded", 3)],
        [],
        [],
    )

    summary = await evidence_service.get_evidence_summary(session, _args(), now=NOW)

    # An unknown completeness value is dropped entirely; a known completeness
    # with an unknown status still counts as a run, and only the status bucket
    # that failed to parse stays empty.
    assert summary.runs_total == 2
    assert summary.completeness.complete == 2
    assert summary.statuses.ok == 0
    assert summary.statuses.error == 0
    assert summary.delivery.pending == 0


@pytest.mark.asyncio
async def test_capture_policy_reports_an_agent_scoped_winning_row() -> None:
    agent_id = uuid4()
    session = _session(
        [],
        [],
        [
            {"mode": "redacted", "agent_id": agent_id},
            {"mode": "full", "agent_id": None},
        ],
        [],
    )

    summary = await evidence_service.get_evidence_summary(session, _args(), now=NOW)

    assert summary.capture_policy.mode == "redacted"
    assert summary.capture_policy.scope == "agent"
    assert summary.capture_policy.agent_overrides == 1


@pytest.mark.asyncio
async def test_every_query_is_scoped_to_the_operator_org() -> None:
    session = _session([], [], [], [])
    args = _args("30d")

    await evidence_service.get_evidence_summary(session, args, now=NOW)

    assert session.execute.await_count == 4
    for call in session.execute.await_args_list:
        assert call.args[1]["org_id"] == args.org_id
    for call in session.execute.await_args_list[:2]:
        assert call.args[1]["window_start"] == NOW - timedelta(hours=720)


@pytest.mark.parametrize(
    ("range_value", "hours"),
    [("24h", 24), ("7d", 168), ("30d", 720)],
)
def test_window_matches_the_requested_range(range_value: EvidenceRange, hours: int) -> None:
    start, end = window_for(range_value, now=NOW)

    assert end == NOW
    assert start == NOW - timedelta(hours=hours)
