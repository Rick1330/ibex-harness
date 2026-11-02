"""Unit tests for the metadata-only deletion evidence service."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest

from app.services import operator_evidence_deletions as deletion_service
from app.services.operator_evidence_deletions import DeletionArgs, window_for

NOW = datetime(2026, 11, 2, 12, 0, tzinfo=UTC)
GENESIS = "0" * 64


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


@dataclass(frozen=True)
class TombstoneRow:
    event: str
    events: int
    last: datetime | None = None


def _tombstone_row(row: TombstoneRow) -> dict[str, object]:
    return {"event_type": row.event, "events": row.events, "last_event_at": row.last}


def _backlog(pending: int = 0, oldest: datetime | None = None) -> _Result:
    return _Result([{"pending": pending, "oldest_pending_at": oldest}])


@dataclass(frozen=True)
class AuditRow:
    entries: int
    first: int | None
    last: int | None
    first_prev: str | None = GENESIS
    first_break: int | None = None
    head: str | None = None


def _audit_row(row: AuditRow) -> _Result:
    return _Result(
        [
            {
                "entries": row.entries,
                "first_seq": row.first,
                "last_seq": row.last,
                "first_prev_hash": row.first_prev,
                "last_row_hash": row.head,
                "first_break": row.first_break,
            }
        ]
    )


def _job_row(status: str, created_at: datetime = NOW) -> dict[str, object]:
    return {"id": uuid4(), "status": status, "created_at": created_at, "finished_at": None}


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
            _tombstone_row(TombstoneRow("forgotten", 3, NOW)),
            _tombstone_row(TombstoneRow("expired", 2, NOW)),
            _tombstone_row(TombstoneRow("purged", 1, NOW)),
            _tombstone_row(TombstoneRow("created", 99)),
        ],
        _backlog(pending=2, oldest=oldest),
        _Result(scalar=4),
        [{"status": "succeeded", "jobs": 1}, {"status": "hold_blocked", "jobs": 1}],
        [_job_row("succeeded"), job],
        [
            {"job_id": job["id"], "store": "postgres", "status": "verified", "verified_absent_at": NOW},
            {"job_id": job["id"], "store": "redis", "status": "pending", "verified_absent_at": None},
        ],
        _Result(),
        _audit_row(AuditRow(4, 1, 4, head="deadbeef")),
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
    receipts_call = session.execute.await_args_list[5]
    assert receipts_call.args[1]["org_id"] == session.execute.await_args_list[0].args[1]["org_id"]
    assert summary.audit.continuity_ok is True
    assert summary.audit.entries == 4
    assert summary.audit.last_row_hash == "deadbeef"
    assert summary.observed_at == NOW


@pytest.mark.asyncio
async def test_a_broken_link_is_reported_with_the_first_broken_seq() -> None:
    session = _session(
        [],
        _backlog(),
        _Result(scalar=0),
        [],
        [],
        _Result(),
        _audit_row(AuditRow(5, 1, 5, first_break=4, head="cafebabe")),
    )

    summary = await deletion_service.get_evidence_deletions(session, _args(), now=NOW)

    assert summary.audit.continuity_ok is False
    assert summary.audit.broken_at_seq == 4
    assert summary.jobs == []


@pytest.mark.asyncio
async def test_a_chain_that_does_not_start_at_one_is_broken_at_its_start() -> None:
    # A ledger whose first row is gone would otherwise look continuous, because
    # there is no earlier row to compare against.
    session = _session(
        [],
        _backlog(),
        _Result(scalar=0),
        [],
        [],
        _Result(),
        _audit_row(AuditRow(3, 2, 4, head="cafebabe")),
    )

    summary = await deletion_service.get_evidence_deletions(session, _args(), now=NOW)

    assert summary.audit.continuity_ok is False
    assert summary.audit.broken_at_seq == 2


@pytest.mark.asyncio
async def test_a_first_row_that_does_not_link_to_genesis_is_broken() -> None:
    session = _session(
        [],
        _backlog(),
        _Result(scalar=0),
        [],
        [],
        _Result(),
        _audit_row(AuditRow(2, 1, 2, first_prev="ab" * 32, head="cafebabe")),
    )

    summary = await deletion_service.get_evidence_deletions(session, _args(), now=NOW)

    assert summary.audit.continuity_ok is False
    assert summary.audit.broken_at_seq == 1


@pytest.mark.asyncio
async def test_an_empty_tenant_reports_zeros_and_an_intact_empty_chain() -> None:
    session = _session(
        [],
        _backlog(),
        _Result(scalar=0),
        [],
        [],
        _Result(),
        _audit_row(AuditRow(0, None, None, first_prev=None)),
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
        _backlog(),
        _Result(scalar=0),
        [],
        [],
        _Result(),
        _audit_row(AuditRow(0, None, None, first_prev=None)),
    )
    args = _args("7d")

    await deletion_service.get_evidence_deletions(session, args, now=NOW)

    # The SET LOCAL has no bind params; every data query must carry the org.
    scoped = [call for call in session.execute.await_args_list if len(call.args) > 1]
    assert len(scoped) == 6
    for call in scoped:
        assert call.args[1]["org_id"] == args.org_id


@pytest.mark.asyncio
async def test_more_than_twenty_jobs_is_marked_truncated() -> None:
    jobs = [_job_row("succeeded", created_at=NOW - timedelta(minutes=index)) for index in range(21)]
    session = _session(
        [],
        _backlog(),
        _Result(scalar=0),
        [{"status": "succeeded", "jobs": 21}],
        jobs,
        [],
        _Result(),
        _audit_row(AuditRow(0, None, None, first_prev=None)),
    )

    summary = await deletion_service.get_evidence_deletions(session, _args(), now=NOW)

    assert len(summary.jobs) == 20
    assert summary.jobs_truncated is True
