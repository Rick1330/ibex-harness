"""Outbox-backed publication state and watermark for operator trace reads."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime
from typing import Any
from uuid import UUID

from apierror_py import SERVICE_DEGRADED
from sqlalchemy import bindparam, column, select, table
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession

from app.errors import ApiError

_WATERMARK_NOT_PROVIDED = "not_provided"
_TRACE_UNAVAILABLE = "Trace data is temporarily unavailable"
_ACTIVE = frozenset({"pending", "in_flight", "delivered"})
_PENDING_ONLY = frozenset({"pending", "in_flight"})

_EVIDENCE_OUTBOX = table(
    "evidence_outbox",
    column("org_id"),
    column("aggregate_id"),
    column("aggregate_seq"),
    column("delivery_status"),
    column("created_at"),
    column("delivered_at"),
    schema="ibex_core",
)


@dataclass(frozen=True, slots=True)
class PublicationMeta:
    publication_state: str
    source_watermark: str
    ingestion_lag_ms: int | None


def _is_poison(unique: frozenset[str]) -> bool:
    return "poison" in unique


def _is_published(unique: frozenset[str]) -> bool:
    return unique == frozenset({"delivered"})


def _is_pending(unique: frozenset[str]) -> bool:
    return bool(unique) and unique <= _PENDING_ONLY


def _is_failed_only(unique: frozenset[str]) -> bool:
    return "failed" in unique and not (unique & _ACTIVE)


def _is_partial(unique: frozenset[str]) -> bool:
    return bool(unique & frozenset({"failed", "delivered", "pending", "in_flight"}))


_STATE_RULES: tuple[tuple[Callable[[frozenset[str]], bool], str], ...] = (
    (_is_poison, "poison"),
    (_is_published, "published"),
    (_is_pending, "pending"),
    (_is_failed_only, "failed"),
    (_is_partial, "partial"),
)


def _publication_state(unique: frozenset[str]) -> str:
    for predicate, state in _STATE_RULES:
        if predicate(unique):
            return state
    return "unavailable"


def map_publication(statuses: list[str], max_seq: int | None, lag_ms: int | None) -> PublicationMeta:
    if not statuses:
        return PublicationMeta("unavailable", _WATERMARK_NOT_PROVIDED, None)
    watermark = f"outbox:{max_seq}" if max_seq is not None else _WATERMARK_NOT_PROVIDED
    return PublicationMeta(_publication_state(frozenset(statuses)), watermark, lag_ms)


def _lag_ms(entries: list[Any], observed_at: datetime) -> int | None:
    lags: list[float] = []
    for entry in entries:
        created = entry["created_at"]
        if created is None:
            continue
        end = entry["delivered_at"] or observed_at
        lags.append((end - created).total_seconds() * 1000)
    if not lags:
        return None
    return max(0, round(max(lags)))


def _meta_for_entries(entries: list[Any], observed_at: datetime) -> PublicationMeta:
    statuses = [str(entry["delivery_status"]) for entry in entries]
    delivered_seqs = (
        int(entry["aggregate_seq"])
        for entry in entries
        if str(entry["delivery_status"]) == "delivered"
    )
    max_seq = max(delivered_seqs, default=None)
    return map_publication(statuses, max_seq, _lag_ms(entries, observed_at))


async def publication_for_requests(
    session: AsyncSession,
    org_id: UUID,
    request_ids: list[str],
    observed_at: datetime,
) -> dict[str, PublicationMeta]:
    if not request_ids:
        return {}
    sql = (
        select(
            _EVIDENCE_OUTBOX.c.aggregate_id,
            _EVIDENCE_OUTBOX.c.aggregate_seq,
            _EVIDENCE_OUTBOX.c.delivery_status,
            _EVIDENCE_OUTBOX.c.created_at,
            _EVIDENCE_OUTBOX.c.delivered_at,
        )
        .where(
            _EVIDENCE_OUTBOX.c.org_id == bindparam("org_id"),
            _EVIDENCE_OUTBOX.c.aggregate_id.in_(bindparam("request_ids", expanding=True)),
        )
        .order_by(_EVIDENCE_OUTBOX.c.aggregate_id, _EVIDENCE_OUTBOX.c.aggregate_seq.desc())
    )
    try:
        result = await session.execute(
            sql,
            {"org_id": str(org_id), "request_ids": list(request_ids)},
        )
        rows = list(result.mappings().all())
    except SQLAlchemyError as exc:
        raise ApiError(code=SERVICE_DEGRADED, message=_TRACE_UNAVAILABLE) from exc

    by_request: dict[str, list[Any]] = {rid: [] for rid in request_ids}
    for row in rows:
        by_request.setdefault(str(row["aggregate_id"]), []).append(row)
    return {rid: _meta_for_entries(entries, observed_at) for rid, entries in by_request.items()}


unavailable_publication = PublicationMeta("unavailable", _WATERMARK_NOT_PROVIDED, None)
