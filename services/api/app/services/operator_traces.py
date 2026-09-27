"""Bounded, tenant-scoped metadata reads for the D2 operator surface."""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import logging
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import UUID

from apierror_py import NOT_FOUND, SERVICE_DEGRADED, VALIDATION_ERROR
from sqlalchemy import bindparam, column, func, select, table, tuple_
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import Settings
from app.errors import ApiError
from app.operator_session_auth import OperatorSessionAuthorization
from app.schemas.operator_traces import (
    OperatorTraceAssemblyMetrics,
    OperatorTraceCandidate,
    OperatorTraceDetailResponse,
    OperatorTraceDirectiveSnapshot,
    OperatorTraceListItem,
    OperatorTraceListQuery,
    OperatorTraceListResponse,
    OperatorTraceSpan,
    OperatorTraceToolAudit,
    TraceEvidenceState,
    UnavailableSection,
)

_LOG = logging.getLogger("ibex.api.operator_traces")
_MAX_PAGE_SIZE = 100
_MAX_RANGE = timedelta(days=7)
_CURSOR_TTL = timedelta(minutes=15)
_TRACE_NOT_FOUND = "Trace not found"
_TRACE_UNAVAILABLE = "Trace data is temporarily unavailable"
_QUERY_SORT = "started_at.desc,trace_id.desc,run_id.desc"
_WATERMARK_NOT_PROVIDED = "not_provided"

_EVIDENCE_RUNS = table(
    "evidence_runs",
    column("id"),
    column("trace_id"),
    column("request_id"),
    column("agent_id"),
    column("session_id"),
    column("checkpoint_id"),
    column("schema_version"),
    column("status"),
    column("error_code"),
    column("capture_mode"),
    column("started_at"),
    column("ended_at"),
    column("completeness"),
    column("sample_decision"),
    column("org_id"),
    schema="ibex_core",
)

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

_EVIDENCE_SPANS = table(
    "evidence_spans",
    column("org_id"),
    column("run_id"),
    column("span_id"),
    column("parent_span_id"),
    column("operation_kind"),
    column("status"),
    column("error_code"),
    column("started_at"),
    column("ended_at"),
    schema="ibex_core",
)

_EVIDENCE_ASSEMBLY = table(
    "evidence_assembly_metrics",
    column("org_id"),
    column("run_id"),
    column("budget_calculation_ms"),
    column("directive_load_ms"),
    column("hot_memory_retrieval_ms"),
    column("cold_memory_retrieval_ms"),
    column("ranking_ms"),
    column("packing_ms"),
    column("formatting_ms"),
    column("total_ms"),
    column("candidates_evaluated"),
    schema="ibex_core",
)

_EVIDENCE_CANDIDATES = table(
    "evidence_score_candidates",
    column("org_id"),
    column("run_id"),
    column("memory_id"),
    column("retrieval_rank"),
    column("final_rank"),
    column("delta_rank"),
    column("category"),
    column("token_estimate"),
    column("exclusion"),
    column("score_schema"),
    column("composite_score"),
    schema="ibex_core",
)

_EVIDENCE_DIRECTIVES = table(
    "evidence_directive_snapshots",
    column("org_id"),
    column("run_id"),
    column("directive_version_id"),
    column("content_hash"),
    column("schema_version"),
    schema="ibex_core",
)

_EVIDENCE_TOOLS = table(
    "evidence_tool_audits",
    column("org_id"),
    column("run_id"),
    column("tool_name"),
    column("status"),
    column("error_code"),
    column("created_at"),
    schema="ibex_core",
)


@dataclass(frozen=True, slots=True)
class _ResolvedListPage:
    """Signed-query page inputs after bounds validation."""

    settings: Settings
    authorization: OperatorSessionAuthorization
    query: OperatorTraceListQuery
    query_start: datetime
    query_end: datetime


@dataclass(frozen=True, slots=True)
class _PublicationMeta:
    publication_state: str
    source_watermark: str
    ingestion_lag_ms: int | None


def _trace_columns() -> tuple[Any, ...]:
    return (
        _EVIDENCE_RUNS.c.id.label("run_id"),
        _EVIDENCE_RUNS.c.trace_id,
        _EVIDENCE_RUNS.c.request_id,
        _EVIDENCE_RUNS.c.agent_id,
        _EVIDENCE_RUNS.c.session_id,
        _EVIDENCE_RUNS.c.checkpoint_id,
        _EVIDENCE_RUNS.c.schema_version,
        _EVIDENCE_RUNS.c.status,
        _EVIDENCE_RUNS.c.error_code,
        _EVIDENCE_RUNS.c.capture_mode,
        _EVIDENCE_RUNS.c.started_at,
        _EVIDENCE_RUNS.c.ended_at,
        _EVIDENCE_RUNS.c.completeness,
        _EVIDENCE_RUNS.c.sample_decision,
    )


def _status_predicate(status: str):
    if status == "ok":
        return _EVIDENCE_RUNS.c.status == "ok"
    if status == "error":
        return _EVIDENCE_RUNS.c.status != "ok"
    raise ApiError(code=VALIDATION_ERROR, message="Invalid trace status filter")


def _normalized_query_fingerprint(query: OperatorTraceListQuery, query_start: datetime, query_end: datetime) -> str:
    parts = [
        f"status={query.status or ''}",
        f"start={_normalize_datetime(query_start).isoformat()}",
        f"end={_normalize_datetime(query_end).isoformat()}",
        f"trace_id={query.trace_id or ''}",
        f"request_id={query.request_id or ''}",
        f"run_id={query.run_id or ''}",
        f"session_id={query.session_id or ''}",
        f"error_code={query.error_code or ''}",
        f"completeness={query.completeness or ''}",
        f"capture_mode={query.capture_mode or ''}",
        f"sort={_QUERY_SORT}",
    ]
    return "&".join(parts)


def _apply_list_filters(sql: Any, query: OperatorTraceListQuery) -> Any:
    if query.status is not None:
        sql = sql.where(_status_predicate(query.status))
    if query.trace_id is not None:
        sql = sql.where(_EVIDENCE_RUNS.c.trace_id == bindparam("filter_trace_id"))
    if query.request_id is not None:
        sql = sql.where(_EVIDENCE_RUNS.c.request_id == bindparam("filter_request_id"))
    if query.run_id is not None:
        sql = sql.where(_EVIDENCE_RUNS.c.id == bindparam("filter_run_id"))
    if query.session_id is not None:
        sql = sql.where(_EVIDENCE_RUNS.c.session_id == bindparam("filter_session_id"))
    if query.error_code is not None:
        sql = sql.where(_EVIDENCE_RUNS.c.error_code == bindparam("filter_error_code"))
    if query.completeness is not None:
        sql = sql.where(_EVIDENCE_RUNS.c.completeness == bindparam("filter_completeness"))
    if query.capture_mode is not None:
        sql = sql.where(_EVIDENCE_RUNS.c.capture_mode == bindparam("filter_capture_mode"))
    return sql


def _filter_params(query: OperatorTraceListQuery) -> dict[str, object]:
    params: dict[str, object] = {}
    if query.trace_id is not None:
        params["filter_trace_id"] = query.trace_id
    if query.request_id is not None:
        params["filter_request_id"] = query.request_id
    if query.run_id is not None:
        params["filter_run_id"] = str(query.run_id)
    if query.session_id is not None:
        params["filter_session_id"] = str(query.session_id)
    if query.error_code is not None:
        params["filter_error_code"] = query.error_code
    if query.completeness is not None:
        params["filter_completeness"] = query.completeness
    if query.capture_mode is not None:
        params["filter_capture_mode"] = query.capture_mode
    return params


def _list_query(query: OperatorTraceListQuery, *, cursor: bool):
    sql = select(*_trace_columns()).where(
        _EVIDENCE_RUNS.c.org_id == bindparam("org_id"),
        _EVIDENCE_RUNS.c.started_at >= bindparam("query_start"),
        _EVIDENCE_RUNS.c.started_at <= bindparam("query_end"),
    )
    sql = _apply_list_filters(sql, query)
    if cursor:
        sql = sql.where(
            tuple_(_EVIDENCE_RUNS.c.started_at, _EVIDENCE_RUNS.c.trace_id, _EVIDENCE_RUNS.c.id)
            < tuple_(
                bindparam("cursor_started"),
                bindparam("cursor_trace"),
                bindparam("cursor_run"),
            )
        )
    return sql.order_by(
        _EVIDENCE_RUNS.c.started_at.desc(),
        _EVIDENCE_RUNS.c.trace_id.desc(),
        _EVIDENCE_RUNS.c.id.desc(),
    ).limit(bindparam("limit"))


def _count_query(query: OperatorTraceListQuery):
    sql = select(func.count()).select_from(_EVIDENCE_RUNS).where(
        _EVIDENCE_RUNS.c.org_id == bindparam("org_id"),
        _EVIDENCE_RUNS.c.started_at >= bindparam("query_start"),
        _EVIDENCE_RUNS.c.started_at <= bindparam("query_end"),
    )
    return _apply_list_filters(sql, query)


def _run_detail_query():
    return select(*_trace_columns()).where(
        _EVIDENCE_RUNS.c.org_id == bindparam("org_id"),
        _EVIDENCE_RUNS.c.id == bindparam("run_id"),
    ).limit(1)


def _trace_runs_query():
    return (
        select(*_trace_columns())
        .where(
            _EVIDENCE_RUNS.c.org_id == bindparam("org_id"),
            _EVIDENCE_RUNS.c.trace_id == bindparam("trace_id"),
        )
        .order_by(_EVIDENCE_RUNS.c.started_at.desc(), _EVIDENCE_RUNS.c.id.desc())
        .limit(bindparam("limit"))
    )


def _cursor_key(settings: Settings) -> bytes:
    value = settings.operator_cursor_secret
    if not value:
        raise ApiError(code=SERVICE_DEGRADED, message="Trace cursor signing is unavailable")
    return value.encode("utf-8")


def _normalize_datetime(value: datetime) -> datetime:
    if value.tzinfo is None:
        raise ApiError(code=VALIDATION_ERROR, message="Trace time range must include a timezone")
    return value.astimezone(UTC)


def _encode_cursor(page: _ResolvedListPage, row: Any) -> str:
    expires_at = datetime.now(UTC) + _CURSOR_TTL
    payload = {
        "org_id": str(page.authorization.org_id),
        "query": _normalized_query_fingerprint(page.query, page.query_start, page.query_end),
        "query_start": _normalize_datetime(page.query_start).isoformat(),
        "query_end": _normalize_datetime(page.query_end).isoformat(),
        "started_at": row["started_at"].isoformat(),
        "trace_id": row["trace_id"],
        "run_id": str(row["run_id"]),
        "expires_at": expires_at.isoformat(),
    }
    encoded = base64.urlsafe_b64encode(json.dumps(payload, separators=(",", ":")).encode()).decode()
    signature = hmac.new(_cursor_key(page.settings), encoded.encode(), hashlib.sha256).hexdigest()
    return f"{encoded}.{signature}"


def _decode_signed_cursor_payload(
    settings: Settings,
    authorization: OperatorSessionAuthorization,
    cursor: str,
) -> dict[str, Any]:
    encoded, signature = cursor.split(".", 1)
    expected = hmac.new(_cursor_key(settings), encoded.encode(), hashlib.sha256).hexdigest()
    if not hmac.compare_digest(signature, expected):
        raise ValueError("signature")
    payload = json.loads(base64.urlsafe_b64decode(encoded.encode()))
    if payload["org_id"] != str(authorization.org_id):
        raise ValueError("tenant")
    expires_at = datetime.fromisoformat(payload["expires_at"])
    if expires_at <= datetime.now(UTC):
        raise ValueError("expired")
    return payload


def _decode_cursor(page: _ResolvedListPage, cursor: str) -> tuple[datetime, str, str]:
    try:
        payload = _decode_signed_cursor_payload(page.settings, page.authorization, cursor)
        expected = _normalized_query_fingerprint(page.query, page.query_start, page.query_end)
        if payload["query"] != expected:
            raise ValueError("query")
        return (
            datetime.fromisoformat(payload["started_at"]),
            str(payload["trace_id"]),
            str(payload["run_id"]),
        )
    except (ApiError, ValueError, KeyError, TypeError, UnicodeError) as exc:
        raise ApiError(code=VALIDATION_ERROR, message="Invalid cursor") from exc


def cursor_query_bounds(
    settings: Settings,
    authorization: OperatorSessionAuthorization,
    cursor: str,
) -> tuple[datetime, datetime]:
    """Return the signed normalized bounds carried by a cursor."""
    try:
        payload = _decode_signed_cursor_payload(settings, authorization, cursor)
        return (
            _normalize_datetime(datetime.fromisoformat(payload["query_start"])),
            _normalize_datetime(datetime.fromisoformat(payload["query_end"])),
        )
    except (ApiError, ValueError, KeyError, TypeError, UnicodeError) as exc:
        raise ApiError(code=VALIDATION_ERROR, message="Invalid cursor") from exc


def _duration_ms(started_at: datetime, ended_at: datetime | None) -> int | None:
    if ended_at is None:
        return None
    return max(0, round((ended_at - started_at).total_seconds() * 1000))


def _map_publication(statuses: list[str], max_seq: int | None, lag_ms: int | None) -> _PublicationMeta:
    if not statuses:
        return _PublicationMeta("unavailable", _WATERMARK_NOT_PROVIDED, None)
    unique = set(statuses)
    watermark = f"outbox:{max_seq}" if max_seq is not None else _WATERMARK_NOT_PROVIDED
    if unique == {"delivered"}:
        return _PublicationMeta("published", watermark, lag_ms)
    if "poison" in unique:
        return _PublicationMeta("poison", watermark, lag_ms)
    if "failed" in unique and not (unique & {"pending", "in_flight", "delivered"}):
        return _PublicationMeta("failed", watermark, lag_ms)
    if "failed" in unique:
        return _PublicationMeta("partial", watermark, lag_ms)
    if unique <= {"pending", "in_flight"}:
        return _PublicationMeta("pending", watermark, lag_ms)
    if "delivered" in unique and (unique & {"pending", "in_flight", "failed"}):
        return _PublicationMeta("partial", watermark, lag_ms)
    return _PublicationMeta("unavailable", watermark, lag_ms)


async def _publication_for_requests(
    session: AsyncSession,
    org_id: UUID,
    request_ids: list[str],
    observed_at: datetime,
) -> dict[str, _PublicationMeta]:
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

    out: dict[str, _PublicationMeta] = {}
    for rid, entries in by_request.items():
        statuses = [str(entry["delivery_status"]) for entry in entries]
        max_seq = max((int(entry["aggregate_seq"]) for entry in entries), default=None)
        lag_ms = None
        delivered = [entry for entry in entries if entry["delivered_at"] is not None]
        if delivered:
            latest = max(delivered, key=lambda entry: entry["delivered_at"])
            lag_ms = max(0, round((observed_at - latest["delivered_at"]).total_seconds() * 1000))
        out[rid] = _map_publication(statuses, max_seq, lag_ms)
    return out


def _evidence(row: Any, observed_at: datetime, publication: _PublicationMeta) -> TraceEvidenceState:
    completeness = str(row["completeness"])
    freshness = "stale" if completeness == "late" else "unknown"
    return TraceEvidenceState(
        schema_version=str(row["schema_version"]),
        capture_mode=str(row["capture_mode"]),
        completeness=completeness,
        sample_decision=str(row["sample_decision"]),
        freshness=freshness,
        retention="unknown",
        source="postgres.evidence_runs",
        source_watermark=publication.source_watermark,
        publication_state=publication.publication_state,  # type: ignore[arg-type]
        ingestion_lag_ms=publication.ingestion_lag_ms,
        observed_at=observed_at,
    )


def _item(row: Any, observed_at: datetime, publication: _PublicationMeta) -> OperatorTraceListItem:
    return OperatorTraceListItem(
        trace_id=str(row["trace_id"]),
        run_id=UUID(str(row["run_id"])),
        request_id=str(row["request_id"]),
        agent_id=UUID(str(row["agent_id"])) if row["agent_id"] else None,
        session_id=UUID(str(row["session_id"])) if row["session_id"] else None,
        checkpoint_id=UUID(str(row["checkpoint_id"])) if row["checkpoint_id"] else None,
        status="error" if str(row["status"]) != "ok" else "ok",
        error_code=str(row["error_code"]) if row["error_code"] else None,
        started_at=row["started_at"],
        ended_at=row["ended_at"],
        duration_ms=_duration_ms(row["started_at"], row["ended_at"]),
        evidence=_evidence(row, observed_at, publication),
    )


def _validate_range_timezone(*values: datetime) -> None:
    if any(value.tzinfo is None for value in values):
        raise ApiError(code=VALIDATION_ERROR, message="Invalid trace time range")


def _validate_range_order(query_start: datetime, query_end: datetime) -> None:
    if query_end <= query_start:
        raise ApiError(code=VALIDATION_ERROR, message="Invalid trace time range")


def _validate_range_size(query_start: datetime, query_end: datetime) -> None:
    if query_end - query_start > _MAX_RANGE:
        raise ApiError(code=VALIDATION_ERROR, message="Trace time range exceeds maximum")


def _validate_range(query_start: datetime, query_end: datetime) -> None:
    _validate_range_timezone(query_start, query_end)
    _validate_range_order(query_start, query_end)
    _validate_range_size(query_start, query_end)


def _resolve_query_bounds(
    settings: Settings,
    authorization: OperatorSessionAuthorization,
    query: OperatorTraceListQuery,
) -> tuple[datetime, datetime]:
    query_start = query.started_after
    query_end = query.started_before
    if query.cursor:
        cursor_start, cursor_end = cursor_query_bounds(settings, authorization, query.cursor)
        query_start = cursor_start if query_start is None else query_start
        query_end = cursor_end if query_end is None else query_end
    resolved_end = query_end or datetime.now(UTC)
    resolved_start = query_start or resolved_end - timedelta(hours=24)
    normalized_start = _normalize_datetime(resolved_start)
    normalized_end = _normalize_datetime(resolved_end)
    _validate_range(normalized_start, normalized_end)
    return normalized_start, normalized_end


def _prepare_list_query(page: _ResolvedListPage) -> tuple[Any, dict[str, object]]:
    params: dict[str, object] = {
        "org_id": str(page.authorization.org_id),
        "query_start": page.query_start,
        "query_end": page.query_end,
        "limit": page.query.limit + 1,
        **_filter_params(page.query),
    }
    if page.query.cursor:
        cursor_started, cursor_trace, cursor_run = _decode_cursor(page, page.query.cursor)
        params.update(
            cursor_started=cursor_started,
            cursor_trace=cursor_trace,
            cursor_run=cursor_run,
        )
    return _list_query(page.query, cursor=bool(page.query.cursor)), params


async def _fetch_rows(session: AsyncSession, query: Any, params: dict[str, object]) -> list[Any]:
    try:
        await session.execute(select(func.set_config("statement_timeout", "3000ms", True)))
        result = await session.execute(query, params)
        return list(result.mappings().all())
    except SQLAlchemyError as exc:
        raise ApiError(code=SERVICE_DEGRADED, message=_TRACE_UNAVAILABLE) from exc


async def _fetch_matched_count(
    session: AsyncSession,
    page: _ResolvedListPage,
) -> int | None:
    params = {
        "org_id": str(page.authorization.org_id),
        "query_start": page.query_start,
        "query_end": page.query_end,
        **_filter_params(page.query),
    }
    try:
        result = await session.execute(_count_query(page.query), params)
        value = result.scalar_one()
        return int(value)
    except SQLAlchemyError:
        return None


def _audit_read(
    authorization: OperatorSessionAuthorization,
    *,
    purpose: str,
    object_id: str,
    outcome: str,
) -> None:
    _LOG.info(
        "operator_trace_read",
        extra={
            "org_id": str(authorization.org_id),
            "subject": authorization.subject,
            "session_id": authorization.session_id,
            "purpose": purpose,
            "object_id": object_id,
            "outcome": outcome,
        },
    )


def _resolved_list_page(
    settings: Settings,
    authorization: OperatorSessionAuthorization,
    query: OperatorTraceListQuery,
) -> _ResolvedListPage:
    if query.limit < 1 or query.limit > _MAX_PAGE_SIZE:
        raise ApiError(code=VALIDATION_ERROR, message="Trace limit must be between 1 and 100")
    query_start, query_end = _resolve_query_bounds(settings, authorization, query)
    return _ResolvedListPage(
        settings=settings,
        authorization=authorization,
        query=query,
        query_start=query_start,
        query_end=query_end,
    )


async def _items_for_rows(
    session: AsyncSession,
    authorization: OperatorSessionAuthorization,
    rows: list[Any],
    observed_at: datetime,
) -> list[OperatorTraceListItem]:
    request_ids = [str(row["request_id"]) for row in rows]
    publications = await _publication_for_requests(
        session, authorization.org_id, request_ids, observed_at
    )
    return [
        _item(
            row,
            observed_at,
            publications.get(
                str(row["request_id"]),
                _PublicationMeta("unavailable", _WATERMARK_NOT_PROVIDED, None),
            ),
        )
        for row in rows
    ]


async def list_operator_traces(
    session: AsyncSession,
    settings: Settings,
    authorization: OperatorSessionAuthorization,
    query: OperatorTraceListQuery,
) -> OperatorTraceListResponse:
    page = _resolved_list_page(settings, authorization, query)
    sql, params = _prepare_list_query(page)
    rows = await _fetch_rows(session, sql, params)
    matched_count = await _fetch_matched_count(session, page)
    observed_at = datetime.now(UTC)
    truncated = len(rows) > page.query.limit
    page_rows = rows[: page.query.limit]
    items = await _items_for_rows(session, authorization, page_rows, observed_at)
    next_cursor = _encode_cursor(page, page_rows[-1]) if truncated else None
    _audit_read(authorization, purpose="list", object_id="traces", outcome="ok")
    return OperatorTraceListResponse(
        items=items,
        next_cursor=next_cursor,
        truncated=truncated,
        matched_count=matched_count,
        returned_count=len(items),
        observed_at=observed_at,
        query_start=page.query_start,
        query_end=page.query_end,
        limit=page.query.limit,
    )


async def list_operator_trace_runs(
    session: AsyncSession,
    authorization: OperatorSessionAuthorization,
    *,
    trace_id: str,
    limit: int = 100,
) -> OperatorTraceListResponse:
    if not trace_id or len(trace_id) > 256:
        raise ApiError(code=NOT_FOUND, message=_TRACE_NOT_FOUND)
    if limit < 1 or limit > _MAX_PAGE_SIZE:
        raise ApiError(code=VALIDATION_ERROR, message="Trace limit must be between 1 and 100")
    observed_at = datetime.now(UTC)
    rows = await _fetch_rows(
        session,
        _trace_runs_query(),
        {"org_id": str(authorization.org_id), "trace_id": trace_id, "limit": limit + 1},
    )
    if not rows:
        _audit_read(authorization, purpose="trace_runs", object_id=trace_id, outcome="not_found")
        raise ApiError(code=NOT_FOUND, message=_TRACE_NOT_FOUND)
    truncated = len(rows) > limit
    page_rows = rows[:limit]
    items = await _items_for_rows(session, authorization, page_rows, observed_at)
    _audit_read(authorization, purpose="trace_runs", object_id=trace_id, outcome="ok")
    return OperatorTraceListResponse(
        items=items,
        next_cursor=None,
        truncated=truncated,
        matched_count=len(items) if not truncated else None,
        returned_count=len(items),
        observed_at=observed_at,
        query_start=datetime.min.replace(tzinfo=UTC),
        query_end=datetime.max.replace(tzinfo=UTC),
        limit=limit,
    )


async def _load_spans(session: AsyncSession, org_id: UUID, run_id: UUID) -> list[OperatorTraceSpan]:
    sql = (
        select(
            _EVIDENCE_SPANS.c.span_id,
            _EVIDENCE_SPANS.c.parent_span_id,
            _EVIDENCE_SPANS.c.operation_kind,
            _EVIDENCE_SPANS.c.status,
            _EVIDENCE_SPANS.c.error_code,
            _EVIDENCE_SPANS.c.started_at,
            _EVIDENCE_SPANS.c.ended_at,
        )
        .where(
            _EVIDENCE_SPANS.c.org_id == bindparam("org_id"),
            _EVIDENCE_SPANS.c.run_id == bindparam("run_id"),
        )
        .order_by(_EVIDENCE_SPANS.c.started_at.asc())
        .limit(500)
    )
    rows = await _fetch_rows(session, sql, {"org_id": str(org_id), "run_id": str(run_id)})
    return [
        OperatorTraceSpan(
            span_id=str(row["span_id"]),
            parent_span_id=str(row["parent_span_id"]) if row["parent_span_id"] else None,
            operation_kind=str(row["operation_kind"]),
            status=str(row["status"]),
            error_code=str(row["error_code"]) if row["error_code"] else None,
            started_at=row["started_at"],
            ended_at=row["ended_at"],
        )
        for row in rows
    ]


async def _load_assembly(
    session: AsyncSession, org_id: UUID, run_id: UUID
) -> OperatorTraceAssemblyMetrics | None:
    sql = select(
        _EVIDENCE_ASSEMBLY.c.budget_calculation_ms,
        _EVIDENCE_ASSEMBLY.c.directive_load_ms,
        _EVIDENCE_ASSEMBLY.c.hot_memory_retrieval_ms,
        _EVIDENCE_ASSEMBLY.c.cold_memory_retrieval_ms,
        _EVIDENCE_ASSEMBLY.c.ranking_ms,
        _EVIDENCE_ASSEMBLY.c.packing_ms,
        _EVIDENCE_ASSEMBLY.c.formatting_ms,
        _EVIDENCE_ASSEMBLY.c.total_ms,
        _EVIDENCE_ASSEMBLY.c.candidates_evaluated,
    ).where(
        _EVIDENCE_ASSEMBLY.c.org_id == bindparam("org_id"),
        _EVIDENCE_ASSEMBLY.c.run_id == bindparam("run_id"),
    ).limit(1)
    rows = await _fetch_rows(session, sql, {"org_id": str(org_id), "run_id": str(run_id)})
    if not rows:
        return None
    row = rows[0]
    return OperatorTraceAssemblyMetrics(
        budget_calculation_ms=int(row["budget_calculation_ms"]),
        directive_load_ms=int(row["directive_load_ms"]),
        hot_memory_retrieval_ms=int(row["hot_memory_retrieval_ms"]),
        cold_memory_retrieval_ms=int(row["cold_memory_retrieval_ms"]),
        ranking_ms=int(row["ranking_ms"]),
        packing_ms=int(row["packing_ms"]),
        formatting_ms=int(row["formatting_ms"]),
        total_ms=int(row["total_ms"]),
        candidates_evaluated=int(row["candidates_evaluated"]),
    )


async def _load_candidates(
    session: AsyncSession, org_id: UUID, run_id: UUID
) -> tuple[list[OperatorTraceCandidate], str | None]:
    sql = (
        select(
            _EVIDENCE_CANDIDATES.c.memory_id,
            _EVIDENCE_CANDIDATES.c.retrieval_rank,
            _EVIDENCE_CANDIDATES.c.final_rank,
            _EVIDENCE_CANDIDATES.c.delta_rank,
            _EVIDENCE_CANDIDATES.c.category,
            _EVIDENCE_CANDIDATES.c.token_estimate,
            _EVIDENCE_CANDIDATES.c.exclusion,
            _EVIDENCE_CANDIDATES.c.score_schema,
            _EVIDENCE_CANDIDATES.c.composite_score,
        )
        .where(
            _EVIDENCE_CANDIDATES.c.org_id == bindparam("org_id"),
            _EVIDENCE_CANDIDATES.c.run_id == bindparam("run_id"),
        )
        .order_by(_EVIDENCE_CANDIDATES.c.retrieval_rank.asc())
        .limit(500)
    )
    rows = await _fetch_rows(session, sql, {"org_id": str(org_id), "run_id": str(run_id)})
    note = None
    if any(str(row["score_schema"]) == "interim_v1" for row in rows):
        note = "Score rows use interim_v1; five-term waterfall explanation is not rendered."
    candidates = [
        OperatorTraceCandidate(
            memory_id=UUID(str(row["memory_id"])),
            retrieval_rank=int(row["retrieval_rank"]),
            final_rank=int(row["final_rank"]) if row["final_rank"] is not None else None,
            delta_rank=int(row["delta_rank"]) if row["delta_rank"] is not None else None,
            category=str(row["category"]) if row["category"] else None,
            token_estimate=int(row["token_estimate"]) if row["token_estimate"] is not None else None,
            exclusion=str(row["exclusion"]),
            score_schema=str(row["score_schema"]),
            composite_score=float(row["composite_score"]) if row["composite_score"] is not None else None,
        )
        for row in rows
    ]
    return candidates, note


async def _load_directive(
    session: AsyncSession, org_id: UUID, run_id: UUID
) -> OperatorTraceDirectiveSnapshot | None:
    sql = select(
        _EVIDENCE_DIRECTIVES.c.directive_version_id,
        _EVIDENCE_DIRECTIVES.c.content_hash,
        _EVIDENCE_DIRECTIVES.c.schema_version,
    ).where(
        _EVIDENCE_DIRECTIVES.c.org_id == bindparam("org_id"),
        _EVIDENCE_DIRECTIVES.c.run_id == bindparam("run_id"),
    ).limit(1)
    rows = await _fetch_rows(session, sql, {"org_id": str(org_id), "run_id": str(run_id)})
    if not rows:
        return None
    row = rows[0]
    return OperatorTraceDirectiveSnapshot(
        directive_version_id=UUID(str(row["directive_version_id"])) if row["directive_version_id"] else None,
        content_hash=str(row["content_hash"]) if row["content_hash"] else None,
        schema_version=str(row["schema_version"]),
    )


async def _load_tools(
    session: AsyncSession, org_id: UUID, run_id: UUID
) -> list[OperatorTraceToolAudit]:
    sql = (
        select(
            _EVIDENCE_TOOLS.c.tool_name,
            _EVIDENCE_TOOLS.c.status,
            _EVIDENCE_TOOLS.c.error_code,
            _EVIDENCE_TOOLS.c.created_at,
        )
        .where(
            _EVIDENCE_TOOLS.c.org_id == bindparam("org_id"),
            _EVIDENCE_TOOLS.c.run_id == bindparam("run_id"),
        )
        .order_by(_EVIDENCE_TOOLS.c.created_at.asc())
        .limit(200)
    )
    rows = await _fetch_rows(session, sql, {"org_id": str(org_id), "run_id": str(run_id)})
    return [
        OperatorTraceToolAudit(
            tool_name=str(row["tool_name"]),
            status=str(row["status"]),
            error_code=str(row["error_code"]) if row["error_code"] else None,
            started_at=row["created_at"],
            ended_at=None,
        )
        for row in rows
    ]


async def get_operator_trace_run(
    session: AsyncSession,
    authorization: OperatorSessionAuthorization,
    *,
    run_id: UUID,
) -> OperatorTraceDetailResponse:
    rows = await _fetch_rows(
        session,
        _run_detail_query(),
        {"org_id": str(authorization.org_id), "run_id": str(run_id)},
    )
    if not rows:
        _audit_read(authorization, purpose="run_detail", object_id=str(run_id), outcome="not_found")
        raise ApiError(code=NOT_FOUND, message=_TRACE_NOT_FOUND)
    observed_at = datetime.now(UTC)
    items = await _items_for_rows(session, authorization, rows, observed_at)
    item = items[0]

    spans = await _load_spans(session, authorization.org_id, run_id)
    assembly = await _load_assembly(session, authorization.org_id, run_id)
    candidates, score_note = await _load_candidates(session, authorization.org_id, run_id)
    directive = await _load_directive(session, authorization.org_id, run_id)
    tools = await _load_tools(session, authorization.org_id, run_id)

    unavailable: list[UnavailableSection] = ["content", "events"]
    if not spans:
        unavailable.append("spans")
    if assembly is None:
        unavailable.append("assembly")
    if not candidates:
        unavailable.append("candidates")
        unavailable.append("score_explanation")
    elif score_note:
        unavailable.append("score_explanation")
    if directive is None:
        unavailable.append("directives")
    if not tools:
        unavailable.append("tools")

    _audit_read(authorization, purpose="run_detail", object_id=str(run_id), outcome="ok")
    return OperatorTraceDetailResponse(
        **item.model_dump(),
        unavailable_sections=tuple(unavailable),
        spans=spans,
        assembly=assembly,
        candidates=candidates,
        directive=directive,
        tools=tools,
        score_schema_note=score_note,
    )


# Back-compat alias used by older unit tests / imports until callers migrate.
async def get_operator_trace(
    session: AsyncSession,
    authorization: OperatorSessionAuthorization,
    *,
    trace_id: str,
) -> OperatorTraceListResponse:
    return await list_operator_trace_runs(session, authorization, trace_id=trace_id)
