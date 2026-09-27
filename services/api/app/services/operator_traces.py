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
    OperatorTraceDetailResponse,
    OperatorTraceListItem,
    OperatorTraceListQuery,
    OperatorTraceListResponse,
    TraceEvidenceState,
)
from app.services.operator_traces_children import (
    fetch_rows,
    load_run_children,
    unavailable_sections,
)
from app.services.operator_traces_publication import (
    PublicationMeta,
    publication_for_requests,
    unavailable_publication,
)

_LOG = logging.getLogger("ibex.api.operator_traces")
_MAX_PAGE_SIZE = 100
_MAX_RANGE = timedelta(days=7)
_CURSOR_TTL = timedelta(minutes=15)
_TRACE_NOT_FOUND = "Trace not found"
_TRACE_UNAVAILABLE = "Trace data is temporarily unavailable"
_QUERY_SORT = "started_at.desc,trace_id.desc,run_id.desc"

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

_EQUAL_FILTERS: tuple[tuple[str, Any, str], ...] = (
    ("trace_id", _EVIDENCE_RUNS.c.trace_id, "filter_trace_id"),
    ("request_id", _EVIDENCE_RUNS.c.request_id, "filter_request_id"),
    ("run_id", _EVIDENCE_RUNS.c.id, "filter_run_id"),
    ("session_id", _EVIDENCE_RUNS.c.session_id, "filter_session_id"),
    ("error_code", _EVIDENCE_RUNS.c.error_code, "filter_error_code"),
    ("completeness", _EVIDENCE_RUNS.c.completeness, "filter_completeness"),
    ("capture_mode", _EVIDENCE_RUNS.c.capture_mode, "filter_capture_mode"),
)


@dataclass(frozen=True, slots=True)
class _ResolvedListPage:
    """Signed-query page inputs after bounds validation."""

    settings: Settings
    authorization: OperatorSessionAuthorization
    query: OperatorTraceListQuery
    query_start: datetime
    query_end: datetime


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
    for attr, col, param in _EQUAL_FILTERS:
        if getattr(query, attr) is not None:
            sql = sql.where(col == bindparam(param))
    return sql


def _filter_params(query: OperatorTraceListQuery) -> dict[str, object]:
    params: dict[str, object] = {}
    for attr, _col, param in _EQUAL_FILTERS:
        value = getattr(query, attr)
        if value is None:
            continue
        params[param] = str(value) if attr in {"run_id", "session_id"} else value
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


def _evidence(row: Any, observed_at: datetime, publication: PublicationMeta) -> TraceEvidenceState:
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


def _item(row: Any, observed_at: datetime, publication: PublicationMeta) -> OperatorTraceListItem:
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


def _validate_range(query_start: datetime, query_end: datetime) -> None:
    if any(value.tzinfo is None for value in (query_start, query_end)):
        raise ApiError(code=VALIDATION_ERROR, message="Invalid trace time range")
    if query_end <= query_start:
        raise ApiError(code=VALIDATION_ERROR, message="Invalid trace time range")
    if query_end - query_start > _MAX_RANGE:
        raise ApiError(code=VALIDATION_ERROR, message="Trace time range exceeds maximum")


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


async def _fetch_matched_count(session: AsyncSession, page: _ResolvedListPage) -> int | None:
    params = {
        "org_id": str(page.authorization.org_id),
        "query_start": page.query_start,
        "query_end": page.query_end,
        **_filter_params(page.query),
    }
    try:
        result = await session.execute(_count_query(page.query), params)
        return int(result.scalar_one())
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
    publications = await publication_for_requests(
        session, authorization.org_id, request_ids, observed_at
    )
    return [
        _item(
            row,
            observed_at,
            publications.get(str(row["request_id"]), unavailable_publication),
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
    rows = await fetch_rows(session, sql, params)
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


def _validate_trace_runs_args(trace_id: str, limit: int) -> None:
    if not trace_id or len(trace_id) > 256:
        raise ApiError(code=NOT_FOUND, message=_TRACE_NOT_FOUND)
    if limit < 1 or limit > _MAX_PAGE_SIZE:
        raise ApiError(code=VALIDATION_ERROR, message="Trace limit must be between 1 and 100")


async def list_operator_trace_runs(
    session: AsyncSession,
    authorization: OperatorSessionAuthorization,
    *,
    trace_id: str,
    limit: int = 100,
) -> OperatorTraceListResponse:
    _validate_trace_runs_args(trace_id, limit)
    observed_at = datetime.now(UTC)
    rows = await fetch_rows(
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


async def get_operator_trace_run(
    session: AsyncSession,
    authorization: OperatorSessionAuthorization,
    *,
    run_id: UUID,
) -> OperatorTraceDetailResponse:
    rows = await fetch_rows(
        session,
        _run_detail_query(),
        {"org_id": str(authorization.org_id), "run_id": str(run_id)},
    )
    if not rows:
        _audit_read(authorization, purpose="run_detail", object_id=str(run_id), outcome="not_found")
        raise ApiError(code=NOT_FOUND, message=_TRACE_NOT_FOUND)
    observed_at = datetime.now(UTC)
    item = (await _items_for_rows(session, authorization, rows, observed_at))[0]
    children = await load_run_children(session, authorization.org_id, run_id)
    spans, assembly, candidates, score_note, directive, tools = children
    _audit_read(authorization, purpose="run_detail", object_id=str(run_id), outcome="ok")
    return OperatorTraceDetailResponse(
        **item.model_dump(),
        unavailable_sections=tuple(unavailable_sections(children)),
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
