"""Tenant-scoped, metadata-only deletion evidence reads.

Four questions, four bounded queries:

1. what was tombstoned in the window (`memory_lifecycle_outbox` deletion events);
2. what the visibility fence holds now (`memories.tombstoned`);
3. whether the erasure saga completed in every store (`org_deletion_jobs` +
   `deletion_store_receipts`);
4. whether the audit chain is structurally continuous (`privacy_audit_ledger`).

Ledger payload, fields, hold reasons, and memory content are never selected.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import UUID

from apierror_py import SERVICE_DEGRADED
from sqlalchemy import and_, bindparam, column, func, or_, select, table, text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession

from app.errors import ApiError
from app.schemas.operator_evidence_deletions import (
    JOBS_LIMIT,
    AuditChainSummary,
    DeletionRange,
    ErasureJob,
    ErasureStatusCounts,
    OperatorEvidenceDeletions,
    StoreReceipt,
    TombstoneEventCounts,
    TombstoneSummary,
)
from app.services.operator_rows import row_value

_RANGE_HOURS: dict[str, int] = {"24h": 24, "7d": 24 * 7, "30d": 24 * 30}
_TOMBSTONE_EVENTS = ("forgotten", "expired", "purged")
_ERASURE_STATUSES = ("pending", "running", "succeeded", "failed", "hold_blocked")
# Mirrors packages/privacyaudit.GenesisPrevHash: the first entry links to zeros.
_GENESIS_PREV_HASH = "0" * 64
# Bounds the whole-ledger scan below the BFF deadline; mirrors operator_overview.
_SET_QUERY_TIMEOUT = text("SET LOCAL statement_timeout = '3000ms'")
_AUDIT_UNAVAILABLE = "Deletion evidence is temporarily unavailable"

_LIFECYCLE_OUTBOX = table(
    "memory_lifecycle_outbox",
    column("org_id"),
    column("memory_id"),
    column("event_type"),
    column("occurred_at"),
    column("delivered_at"),
    schema="ibex_core",
)

_MEMORIES = table(
    "memories",
    column("org_id"),
    column("tombstoned"),
    schema="ibex_core",
)

_DELETION_JOBS = table(
    "org_deletion_jobs",
    column("id"),
    column("org_id"),
    column("status"),
    column("created_at"),
    column("finished_at"),
    schema="ibex_core",
)

_RECEIPTS = table(
    "deletion_store_receipts",
    column("job_id"),
    column("store"),
    column("status"),
    column("verified_absent_at"),
    schema="ibex_core",
)

_AUDIT = table(
    "privacy_audit_ledger",
    column("org_id"),
    column("seq"),
    column("prev_hash"),
    column("row_hash"),
    schema="ibex_core",
)


@dataclass(frozen=True)
class DeletionArgs:
    org_id: UUID
    range: DeletionRange


def window_for(range_value: DeletionRange, *, now: datetime | None = None) -> tuple[datetime, datetime]:
    end = now or datetime.now(UTC)
    return end - timedelta(hours=_RANGE_HOURS[range_value]), end


def _tombstone_statement() -> Any:
    """Windowed counts per event type, plus the all-time undelivered backlog.

    The backlog is deliberately *not* window-scoped: "nothing is pending" is a
    current fact, and a window-scoped zero would claim delivery while an older
    event is still stuck.
    """
    return (
        select(
            _LIFECYCLE_OUTBOX.c.event_type,
            func.count().label("events"),
            func.max(_LIFECYCLE_OUTBOX.c.occurred_at).label("last_event_at"),
        )
        .select_from(_LIFECYCLE_OUTBOX)
        .where(
            and_(
                _LIFECYCLE_OUTBOX.c.org_id == bindparam("org_id"),
                _LIFECYCLE_OUTBOX.c.occurred_at >= bindparam("window_start"),
                _LIFECYCLE_OUTBOX.c.event_type.in_(_TOMBSTONE_EVENTS),
            )
        )
        .group_by(_LIFECYCLE_OUTBOX.c.event_type)
    )


def _backlog_statement() -> Any:
    return (
        select(
            func.count().label("pending"),
            func.min(_LIFECYCLE_OUTBOX.c.occurred_at).label("oldest_pending_at"),
        )
        .select_from(_LIFECYCLE_OUTBOX)
        .where(
            and_(
                _LIFECYCLE_OUTBOX.c.org_id == bindparam("org_id"),
                _LIFECYCLE_OUTBOX.c.delivered_at.is_(None),
                _LIFECYCLE_OUTBOX.c.event_type.in_(_TOMBSTONE_EVENTS),
            )
        )
    )


def _tombstone_summary(rows: list[Any], backlog: Any, fence: int) -> TombstoneSummary:
    counts: dict[str, int] = {}
    last: list[datetime] = []
    for row in rows:
        counts[str(row_value(row, "event_type"))] = int(row_value(row, "events"))
        if row_value(row, "last_event_at") is not None:
            last.append(row_value(row, "last_event_at"))
    return TombstoneSummary(
        events=TombstoneEventCounts(
            forgotten=counts.get("forgotten", 0),
            expired=counts.get("expired", 0),
            purged=counts.get("purged", 0),
        ),
        pending=int(row_value(backlog, "pending") or 0) if backlog is not None else 0,
        oldest_pending_at=(
            row_value(backlog, "oldest_pending_at") if backlog is not None else None
        ),
        last_event_at=max(last) if last else None,
        tombstoned_memories=fence,
    )


def _fence_statement() -> Any:
    return (
        select(func.count())
        .select_from(_MEMORIES)
        .where(
            _MEMORIES.c.org_id == bindparam("org_id"),
            _MEMORIES.c.tombstoned.is_(True),
        )
    )


def _erasure_statement() -> Any:
    return (
        select(_DELETION_JOBS.c.status, func.count().label("jobs"))
        .select_from(_DELETION_JOBS)
        .where(
            _DELETION_JOBS.c.org_id == bindparam("org_id"),
            _DELETION_JOBS.c.created_at >= bindparam("window_start"),
        )
        .group_by(_DELETION_JOBS.c.status)
    )


def _erasure_counts(rows: list[Any]) -> ErasureStatusCounts:
    counts: dict[str, int] = {}
    for row in rows:
        value = str(row_value(row, "status"))
        if value in _ERASURE_STATUSES:
            counts[value] = int(row_value(row, "jobs"))
    return ErasureStatusCounts(**counts)


def _jobs_statement() -> Any:
    return (
        select(
            _DELETION_JOBS.c.id,
            _DELETION_JOBS.c.status,
            _DELETION_JOBS.c.created_at,
            _DELETION_JOBS.c.finished_at,
        )
        .select_from(_DELETION_JOBS)
        .where(
            _DELETION_JOBS.c.org_id == bindparam("org_id"),
            _DELETION_JOBS.c.created_at >= bindparam("window_start"),
        )
        .order_by(_DELETION_JOBS.c.created_at.desc())
        .limit(JOBS_LIMIT + 1)
    )


def _receipts_statement(job_ids: list[Any]) -> Any:
    """Receipts carry no org column, so the tenant predicate comes from the job."""
    return (
        select(
            _RECEIPTS.c.job_id,
            _RECEIPTS.c.store,
            _RECEIPTS.c.status,
            _RECEIPTS.c.verified_absent_at,
        )
        .select_from(
            _RECEIPTS.join(_DELETION_JOBS, _DELETION_JOBS.c.id == _RECEIPTS.c.job_id)
        )
        .where(
            _RECEIPTS.c.job_id.in_(job_ids),
            _DELETION_JOBS.c.org_id == bindparam("org_id"),
        )
        .order_by(_RECEIPTS.c.store.asc())
    )


def _erasure_jobs(job_rows: list[Any], receipt_rows: list[Any]) -> tuple[list[ErasureJob], bool]:
    by_job: dict[Any, list[StoreReceipt]] = {}
    for row in receipt_rows:
        by_job.setdefault(row_value(row, "job_id"), []).append(
            StoreReceipt(
                store=row_value(row, "store"),
                status=row_value(row, "status"),
                verified_absent_at=row_value(row, "verified_absent_at"),
            )
        )
    jobs = [
        ErasureJob(
            id=str(row_value(row, "id")),
            status=row_value(row, "status"),
            created_at=row_value(row, "created_at"),
            finished_at=row_value(row, "finished_at"),
            receipts=by_job.get(row_value(row, "id"), []),
        )
        for row in job_rows[:JOBS_LIMIT]
    ]
    return jobs, len(job_rows) > JOBS_LIMIT


def _audit_statement() -> Any:
    """One statement, one snapshot: totals, the first break, and the head.

    A single statement keeps the reported totals, break, and last hash from
    disagreeing when an entry commits mid-read. Only structural facts are read;
    the payload is never selected.
    """
    edges = (
        select(
            _AUDIT.c.seq,
            _AUDIT.c.prev_hash,
            func.lag(_AUDIT.c.row_hash).over(order_by=_AUDIT.c.seq).label("prior_hash"),
            func.lag(_AUDIT.c.seq).over(order_by=_AUDIT.c.seq).label("prior_seq"),
        )
        .select_from(_AUDIT)
        .where(_AUDIT.c.org_id == bindparam("org_id"))
        .subquery("audit_edges")
    )
    stats = (
        select(
            func.count().label("entries"),
            func.min(_AUDIT.c.seq).label("first_seq"),
            func.max(_AUDIT.c.seq).label("last_seq"),
        )
        .select_from(_AUDIT)
        .where(_AUDIT.c.org_id == bindparam("org_id"))
        .subquery("audit_stats")
    )
    first_edge = (
        select(_AUDIT.c.prev_hash)
        .select_from(_AUDIT)
        .where(_AUDIT.c.org_id == bindparam("org_id"))
        .order_by(_AUDIT.c.seq.asc())
        .limit(1)
        .scalar_subquery()
    )
    head = (
        select(_AUDIT.c.row_hash)
        .select_from(_AUDIT)
        .where(_AUDIT.c.org_id == bindparam("org_id"))
        .order_by(_AUDIT.c.seq.desc())
        .limit(1)
        .scalar_subquery()
    )
    first_break = (
        select(func.min(edges.c.seq))
        .select_from(edges)
        .where(
            edges.c.prior_seq.is_not(None),
            or_(
                edges.c.seq != edges.c.prior_seq + 1,
                edges.c.prev_hash != edges.c.prior_hash,
            ),
        )
        .scalar_subquery()
    )
    return select(
        stats.c.entries,
        stats.c.first_seq,
        stats.c.last_seq,
        first_edge.label("first_prev_hash"),
        head.label("last_row_hash"),
        first_break.label("first_break"),
    ).select_from(stats)


def _audit_from_row(row: Any) -> AuditChainSummary:
    entries = int(row_value(row, "entries") or 0) if row is not None else 0
    first_seq = row_value(row, "first_seq") if row is not None else None
    last_seq = row_value(row, "last_seq") if row is not None else None
    first_prev = row_value(row, "first_prev_hash") if row is not None else None
    first_break = row_value(row, "first_break") if row is not None else None
    last_hash = row_value(row, "last_row_hash") if row is not None else None

    # A chain is only continuous if it starts at seq 1 and links to the genesis
    # hash; skipping the first row would accept a ledger whose beginning is gone.
    if entries == 0:
        return AuditChainSummary(continuity_ok=True)
    if first_seq != 1 or first_prev != _GENESIS_PREV_HASH:
        return AuditChainSummary(
            entries=entries,
            first_seq=first_seq,
            last_seq=last_seq,
            continuity_ok=False,
            broken_at_seq=first_seq,
            last_row_hash=last_hash,
        )
    return AuditChainSummary(
        entries=entries,
        first_seq=first_seq,
        last_seq=last_seq,
        continuity_ok=first_break is None,
        broken_at_seq=first_break,
        last_row_hash=last_hash,
    )


async def _audit_summary(session: AsyncSession, org_id: UUID) -> AuditChainSummary:
    """Structural continuity of the chain, under a statement deadline.

    The scan is O(org ledger size); the timeout bounds the connection even after
    the Console stops waiting. Content verification stays with the CLI verifier.
    """
    try:
        await session.execute(_SET_QUERY_TIMEOUT)
        row = (
            await session.execute(_audit_statement(), {"org_id": org_id})
        ).mappings().first()
    except SQLAlchemyError as exc:
        raise ApiError(code=SERVICE_DEGRADED, message=_AUDIT_UNAVAILABLE) from exc
    return _audit_from_row(row)


async def get_evidence_deletions(
    session: AsyncSession,
    args: DeletionArgs,
    *,
    now: datetime | None = None,
) -> OperatorEvidenceDeletions:
    window_start, window_end = window_for(args.range, now=now)
    params = {"org_id": args.org_id, "window_start": window_start}

    tombstone_rows = (await session.execute(_tombstone_statement(), params)).mappings().all()
    backlog = (
        await session.execute(_backlog_statement(), {"org_id": args.org_id})
    ).mappings().first()
    fence = (
        await session.execute(_fence_statement(), {"org_id": args.org_id})
    ).scalar_one()
    erasure_rows = (await session.execute(_erasure_statement(), params)).mappings().all()
    job_rows = list((await session.execute(_jobs_statement(), params)).mappings().all())
    job_ids = [row_value(row, "id") for row in job_rows[:JOBS_LIMIT]]
    receipt_rows = (
        (
            await session.execute(
                _receipts_statement(job_ids), {"org_id": args.org_id}
            )
        ).mappings().all()
        if job_ids
        else []
    )
    jobs, jobs_truncated = _erasure_jobs(job_rows, receipt_rows)
    audit = await _audit_summary(session, args.org_id)

    return OperatorEvidenceDeletions(
        range=args.range,
        window_start=window_start,
        window_end=window_end,
        observed_at=window_end,
        tombstones=_tombstone_summary(tombstone_rows, backlog, int(fence)),
        erasures=_erasure_counts(erasure_rows),
        jobs=jobs,
        jobs_truncated=jobs_truncated,
        audit=audit,
    )
