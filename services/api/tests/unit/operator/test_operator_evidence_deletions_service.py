"""Unit tests for the metadata-only deletion evidence service."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest

from app.services import operator_evidence_deletions as deletion_service
from app.services.operator_evidence_deletions import DeletionArgs, window_for

NOW = datetime(2026, 11, 2, 12, 0, tzinfo=UTC)


class _Result:
    def __init__(
        self,
        rows: list[dict[str, object]] | None = None,
        scalar: object = None,
    ) -> None:
        self._rows = rows or []
        self._scalar = scalar

    def mappings(self) -> _Result:
        return self

    def all(self) -> list[dict[str, object]]:
        return list(self._rows)

    def first(self) -> dict[str, object] | None:
        return self._rows[0] if self._rows else None

    def scalar_one(self) -> object:
        return self._scalar

    def scalar_one_or_none(self) -> object:
        return self._scalar


def _session(*results: _Result | list[dict[str, object]]) -> AsyncMock:
    session = AsyncMock()
    session.execute = AsyncMock(
        side_effect=[result if isinstance(result, _Result) else _Result(result) for result in results]
    )
    return session


def _args(range_value: str = "24h") -> DeletionArgs:
    return DeletionArgs(org_id=uuid4(), range=range_value)  # type: ignore[arg-type]


def _tombstone_row(
    event: str,
    events: int,
    pending: int = 0,
    oldest: datetime | None = None,
    last: datetime | None = None,
) -> dict[str, object]:
    return {
        "event_type": event,
        "events": events,
        "pending": pending,
        "oldest_pending_at": oldest,
        "last_event_at": last,
    }


def _job_row(status: str, created_at: datetime = NOW) -> dict[str, object]:
    return {
        "id": uuid4(),
        "status": status,
        "created_at": created_at,
        "finished_at": None,
    }


def _audit_totals(entries: int, first: int | None, last: int | None) -> _Result:
    return _Result([{"entries": entries, "first_seq": first, "last_seq": last}])


@pytest.mark.parametrize(
    ("range_value", "hours"),
    [("24h", 24), ("7d", 168), ("30d", 720)],
)
def test_window_matches_the_requested_range(range_value: str, hours: int) -> None:
    start, end = window_for(range_value, now=NOW)  # type: ignore[arg-type]

    assert end == NOW
    assert start == NOW - timedelta(hours=hours)


@pytest.mark.asyncio
async def test_summary_projects_tombstones_fence_erasures_and_audit() -> None:
    oldest = NOW - timedelta(hours=2)
    job = _job_row("hold_blocked")
    session = _session(
        [
            _tombstone_row("forgotten", 3, pending=0, last=NOW),
            _tombstone_row("expired", 2, pending=1, oldest=oldest, last=NOW),
            _tombstone_row("purged", 1, pending=1, oldest=oldest, last=NOW),
            _tombstone_row("created", 99),
        ],
        _Result(scalar=4),
        [{"status": "succeeded", "jobs": 1}, {"status": "hold_blocked", "jobs": 1}],
        [_job_row("succeeded"), job],
        [
            {"job_id": job["id"], "store": "postgres", "status": "verified", "verified_absent_at": NOW},
            {"job_id": job["id"], "store": "redis", "status": "pending", "verified_absent_at": None},
        ],
        _audit_totals(2, 1, 2),
        _Result(scalar=None),
        _Result(scalar="deadbeef"),
    )

    summary = await deletion_service.get_evidence_deletions(session, _args(), now=NOW)

    assert summary.schema_version == "operator.evidence.deletions.v1"
    assert summary.tombstones.events.model_dump() == {
        "forgotten": 3,
        "expired": 2,
        "purged": 1,
    }
    assert summary.tombstones.pending == 2
    assert summary.tombstones.oldest_pending_at == oldest
    assert summary.tombstones.tombstoned_memories == 4
    assert summary.erasures.succeeded == 1
    assert summary.erasures.hold_blocked == 1
    assert [item.status for item in summary.jobs] == ["succeeded", "hold_blocked"]
    assert [(receipt.store, receipt.status) for receipt in summary.jobs[1].receipts] == [
        ("postgres", "verified"),
        ("redis", "pending"),
    ]
    assert summary.audit.continuity_ok is True
    assert summary.audit.entries == 2
    assert summary.audit.last_row_hash == "deadbeef"
    assert summary.observed_at == NOW


@pytest.mark.asyncio
async def test_a_broken_chain_is_reported_with_the_first_broken_seq() -> None:
    session = _session(
        [],
        _Result(scalar=0),
        [],
        [],
        _audit_totals(5, 1, 5),
        _Result(scalar=4),
        _Result(scalar="cafebabe"),
    )

    summary = await deletion_service.get_evidence_deletions(session, _args(), now=NOW)

    assert summary.audit.continuity_ok is False
    assert summary.audit.broken_at_seq == 4
    assert summary.jobs == []


@pytest.mark.asyncio
async def test_an_empty_tenant_reports_zeros_and_an_intact_empty_chain() -> None:
    session = _session(
        [],
        _Result(scalar=0),
        [],
        [],
        _audit_totals(0, None, None),
        _Result(scalar=None),
        _Result(scalar=None),
    )

    summary = await deletion_service.get_evidence_deletions(session, _args(), now=NOW)

    assert summary.tombstones.events.forgotten == 0
    assert summary.tombstones.pending == 0
    assert summary.tombstones.last_event_at is None
    assert summary.erasures.model_dump() == {
        "pending": 0,
        "running": 0,
        "succeeded": 0,
        "failed": 0,
        "hold_blocked": 0,
    }
    assert summary.audit.entries == 0
    assert summary.audit.continuity_ok is True
    assert summary.audit.first_seq is None


@pytest.mark.asyncio
async def test_every_query_is_scoped_to_the_operator_org() -> None:
    session = _session(
        [],
        _Result(scalar=0),
        [],
        [],
        _audit_totals(0, None, None),
        _Result(scalar=None),
        _Result(scalar=None),
    )
    args = _args("7d")

    await deletion_service.get_evidence_deletions(session, args, now=NOW)

    for call in session.execute.await_args_list:
        assert call.args[1]["org_id"] == args.org_id


@pytest.mark.asyncio
async def test_more_than_twenty_jobs_is_marked_truncated() -> None:
    jobs = [_job_row("succeeded", created_at=NOW - timedelta(minutes=index)) for index in range(21)]
    session = _session(
        [],
        _Result(scalar=0),
        [{"status": "succeeded", "jobs": 21}],
        jobs,
        [],
        _audit_totals(0, None, None),
        _Result(scalar=None),
        _Result(scalar=None),
    )

    summary = await deletion_service.get_evidence_deletions(session, _args(), now=NOW)

    assert len(summary.jobs) == 20
    assert summary.jobs_truncated is True
