"""Tenant-scoped, metadata-only operator evidence summary reads.

Four independent facts, four queries:

1. `evidence_runs` completeness and status, grouped for the window.
2. `evidence_outbox` delivery state for the same window.
3. the effective `org_capture_policies` row.
4. the active `legal_holds` row, if any.

They are deliberately not joined. The outbox carries no run reference, so a
per-run delivery claim would be invented; and a hold changes retention, not
capture completeness.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any, get_args
from uuid import UUID

from sqlalchemy import and_, bindparam, column, func, select, table
from sqlalchemy.ext.asyncio import AsyncSession

from app.schemas.operator_evidence import (
    EvidenceCaptureMode,
    EvidenceCapturePolicy,
    EvidenceCompleteness,
    EvidenceCompletenessCounts,
    EvidenceDeliveryCounts,
    EvidenceDeliveryStatus,
    EvidenceLegalHold,
    EvidenceRange,
    EvidenceRunStatus,
    EvidenceStatusCounts,
    OperatorEvidenceSummary,
)
from app.services.operator_rows import row_value

_RANGE_HOURS: dict[str, int] = {"24h": 24, "7d": 24 * 7, "30d": 24 * 30}

_COMPLETENESS_VALUES: frozenset[str] = frozenset(get_args(EvidenceCompleteness))
_RUN_STATUS_VALUES: frozenset[str] = frozenset(get_args(EvidenceRunStatus))
_DELIVERY_VALUES: frozenset[str] = frozenset(get_args(EvidenceDeliveryStatus))
_CAPTURE_MODE_VALUES: frozenset[str] = frozenset(get_args(EvidenceCaptureMode))
_UNDELIVERED = ("pending", "in_flight", "failed", "poison")

_RUNS = table(
    "evidence_runs",
    column("org_id"),
    column("completeness"),
    column("status"),
    column("started_at"),
    schema="ibex_core",
)

_OUTBOX = table(
    "evidence_outbox",
    column("org_id"),
    column("delivery_status"),
    column("created_at"),
    column("delivered_at"),
    schema="ibex_core",
)

_CAPTURE_POLICIES = table(
    "org_capture_policies",
    column("org_id"),
    column("agent_id"),
    column("mode"),
    column("priority"),
    column("created_at"),
    schema="ibex_core",
)

_LEGAL_HOLDS = table(
    "legal_holds",
    column("org_id"),
    column("created_at"),
    column("cleared_at"),
    schema="ibex_core",
)


@dataclass(frozen=True)
class EvidenceSummaryArgs:
    org_id: UUID
    range: EvidenceRange


def window_for(range_value: EvidenceRange, *, now: datetime | None = None) -> tuple[datetime, datetime]:
    end = now or datetime.now(UTC)
    return end - timedelta(hours=_RANGE_HOURS[range_value]), end


def _runs_statement() -> Any:
    return (
        select(
            _RUNS.c.completeness,
            _RUNS.c.status,
            func.count().label("row_count"),
            func.max(_RUNS.c.started_at).label("last_run_at"),
        )
        .select_from(_RUNS)
        .where(
            and_(
                _RUNS.c.org_id == bindparam("org_id"),
                _RUNS.c.started_at >= bindparam("window_start"),
            )
        )
        .group_by(_RUNS.c.completeness, _RUNS.c.status)
    )


def _delivery_statement() -> Any:
    return (
        select(
            _OUTBOX.c.delivery_status,
            func.count().label("row_count"),
            func.min(_OUTBOX.c.created_at)
            .filter(_OUTBOX.c.delivery_status.in_(_UNDELIVERED))
            .label("oldest_unsettled_at"),
            func.max(_OUTBOX.c.delivered_at).label("last_delivered_at"),
        )
        .select_from(_OUTBOX)
        .where(
            and_(
                _OUTBOX.c.org_id == bindparam("org_id"),
                _OUTBOX.c.created_at >= bindparam("window_start"),
            )
        )
        .group_by(_OUTBOX.c.delivery_status)
    )


def _capture_policy_statement() -> Any:
    return (
        select(_CAPTURE_POLICIES.c.mode, _CAPTURE_POLICIES.c.agent_id)
        .select_from(_CAPTURE_POLICIES)
        .where(_CAPTURE_POLICIES.c.org_id == bindparam("org_id"))
        .order_by(_CAPTURE_POLICIES.c.priority.asc(), _CAPTURE_POLICIES.c.created_at.asc())
    )


def _legal_hold_statement() -> Any:
    return (
        select(_LEGAL_HOLDS.c.created_at)
        .select_from(_LEGAL_HOLDS)
        .where(
            and_(
                _LEGAL_HOLDS.c.org_id == bindparam("org_id"),
                _LEGAL_HOLDS.c.cleared_at.is_(None),
            )
        )
        .order_by(_LEGAL_HOLDS.c.created_at.desc())
        .limit(1)
    )


def _counted_run_rows(rows: list[Any]) -> list[Any]:
    """Rows whose completeness this contract can name.

    Both distributions describe the same row set, so a row with a value the
    contract does not know is dropped from both rather than counted on one axis
    and skipped on the other. The table has CHECK constraints on both columns,
    so this only fires if the schema and the contract drift apart.
    """
    return [row for row in rows if str(row_value(row, "completeness")) in _COMPLETENESS_VALUES]


def _completeness_counts(rows: list[Any]) -> EvidenceCompletenessCounts:
    buckets: dict[str, int] = {}
    for row in rows:
        value = str(row_value(row, "completeness"))
        buckets[value] = buckets.get(value, 0) + int(row_value(row, "row_count"))
    return EvidenceCompletenessCounts(**buckets)


def _status_counts(rows: list[Any]) -> EvidenceStatusCounts:
    buckets: dict[str, int] = {}
    for row in rows:
        value = str(row_value(row, "status"))
        if value in _RUN_STATUS_VALUES:
            buckets[value] = buckets.get(value, 0) + int(row_value(row, "row_count"))
    return EvidenceStatusCounts(**buckets)


def _last_run_at(rows: list[Any]) -> datetime | None:
    stamps = [row_value(row, "last_run_at") for row in rows]
    present = [stamp for stamp in stamps if stamp is not None]
    return max(present) if present else None


def _delivery_counts(rows: list[Any]) -> EvidenceDeliveryCounts:
    buckets: dict[str, int] = {}
    for row in rows:
        value = str(row_value(row, "delivery_status"))
        if value in _DELIVERY_VALUES:
            buckets[value] = buckets.get(value, 0) + int(row_value(row, "row_count"))
    return EvidenceDeliveryCounts(**buckets)


def _oldest_unsettled_at(rows: list[Any]) -> datetime | None:
    stamps = [row_value(row, "oldest_unsettled_at") for row in rows]
    present = [stamp for stamp in stamps if stamp is not None]
    return min(present) if present else None


def _last_delivered_at(rows: list[Any]) -> datetime | None:
    stamps = [row_value(row, "last_delivered_at") for row in rows]
    present = [stamp for stamp in stamps if stamp is not None]
    return max(present) if present else None


def _capture_policy(rows: list[Any]) -> EvidenceCapturePolicy:
    """Report the organization row and count the agent rows.

    Agent policies resolve per agent (`capture_policies.resolve` prefers the
    agent row, then priority), so picking the lowest-priority row overall would
    let one agent override speak for the whole organization.
    """
    agent_overrides = sum(1 for row in rows if row_value(row, "agent_id") is not None)
    organization_row = next(
        (row for row in rows if row_value(row, "agent_id") is None), None
    )
    if organization_row is None:
        return EvidenceCapturePolicy(mode=None, agent_overrides=agent_overrides)
    mode = str(row_value(organization_row, "mode"))
    return EvidenceCapturePolicy(
        mode=mode if mode in _CAPTURE_MODE_VALUES else None,
        agent_overrides=agent_overrides,
    )


def _legal_hold(rows: list[Any]) -> EvidenceLegalHold:
    if not rows:
        return EvidenceLegalHold(active=False, since=None)
    return EvidenceLegalHold(active=True, since=row_value(rows[0], "created_at"))


async def get_evidence_summary(
    session: AsyncSession,
    args: EvidenceSummaryArgs,
    *,
    now: datetime | None = None,
) -> OperatorEvidenceSummary:
    window_start, window_end = window_for(args.range, now=now)
    params = {"org_id": args.org_id, "window_start": window_start}

    run_rows = (await session.execute(_runs_statement(), params)).mappings().all()
    delivery_rows = (await session.execute(_delivery_statement(), params)).mappings().all()
    policy_rows = (await session.execute(_capture_policy_statement(), params)).mappings().all()
    hold_rows = (await session.execute(_legal_hold_statement(), params)).mappings().all()

    counted_runs = _counted_run_rows(run_rows)
    completeness = _completeness_counts(counted_runs)
    return OperatorEvidenceSummary(
        range=args.range,
        window_start=window_start,
        window_end=window_end,
        observed_at=window_end,
        runs_total=sum(
            getattr(completeness, value) for value in _COMPLETENESS_VALUES
        ),
        capture_complete_runs=completeness.complete,
        completeness=completeness,
        statuses=_status_counts(counted_runs),
        last_run_at=_last_run_at(counted_runs),
        delivery=_delivery_counts(delivery_rows),
        oldest_unsettled_at=_oldest_unsettled_at(delivery_rows),
        last_delivered_at=_last_delivered_at(delivery_rows),
        capture_policy=_capture_policy(policy_rows),
        legal_hold=_legal_hold(hold_rows),
    )
