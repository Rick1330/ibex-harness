"""Bounded, tenant-scoped metadata reads for the D2 operator surface."""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import UUID

from apierror_py import NOT_FOUND, SERVICE_DEGRADED, VALIDATION_ERROR
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import Settings
from app.errors import ApiError
from app.operator_session_auth import OperatorSessionAuthorization
from app.schemas.operator_traces import (
    OperatorTraceDetailResponse,
    OperatorTraceListItem,
    OperatorTraceListResponse,
    TraceEvidenceState,
)

_MAX_PAGE_SIZE = 100
_MAX_RANGE = timedelta(days=7)
_CURSOR_TTL = timedelta(minutes=15)
_TRACE_NOT_FOUND = "Trace not found"
_TRACE_UNAVAILABLE = "Trace data is temporarily unavailable"

_BASE_SELECT = """
    SELECT id AS run_id, trace_id, request_id, agent_id, session_id, checkpoint_id,
           status, error_code, started_at, ended_at, completeness, sample_decision
    FROM ibex_core.evidence_runs
    WHERE org_id = :org_id
      AND started_at >= :query_start
      AND started_at <= :query_end
"""
_LIST_QUERY = text(_BASE_SELECT + " ORDER BY started_at DESC, trace_id DESC LIMIT :limit")
_LIST_STATUS_QUERY = text(_BASE_SELECT + " AND status = :status ORDER BY started_at DESC, trace_id DESC LIMIT :limit")
_LIST_CURSOR_QUERY = text(_BASE_SELECT + " AND (started_at, trace_id) < (:cursor_started, :cursor_trace) ORDER BY started_at DESC, trace_id DESC LIMIT :limit")
_LIST_STATUS_CURSOR_QUERY = text(_BASE_SELECT + " AND status = :status AND (started_at, trace_id) < (:cursor_started, :cursor_trace) ORDER BY started_at DESC, trace_id DESC LIMIT :limit")
_DETAIL_QUERY = text(_BASE_SELECT + " AND trace_id = :trace_id ORDER BY started_at DESC LIMIT 1")


def _cursor_key(settings: Settings) -> bytes:
    value = settings.operator_cursor_secret
    if not value:
        raise ApiError(code=SERVICE_DEGRADED, message="Trace cursor signing is unavailable")
    return value.encode("utf-8")


def _normalize_datetime(value: datetime) -> datetime:
    if value.tzinfo is None:
        raise ApiError(code=VALIDATION_ERROR, message="Trace time range must include a timezone")
    return value.astimezone(UTC)


def _query_fingerprint(status: str | None, query_start: datetime, query_end: datetime) -> str:
    start = _normalize_datetime(query_start).isoformat()
    end = _normalize_datetime(query_end).isoformat()
    return f"status={status or ''}&start={start}&end={end}&sort=started_at.desc,trace_id.desc"


def _encode_cursor(
    settings: Settings,
    authorization: OperatorSessionAuthorization,
    status: str | None,
    query_start: datetime,
    query_end: datetime,
    row: Any,
) -> str:
    expires_at = datetime.now(UTC) + _CURSOR_TTL
    payload = {
        "org_id": str(authorization.org_id),
        "query": _query_fingerprint(status, query_start, query_end),
        "query_start": _normalize_datetime(query_start).isoformat(),
        "query_end": _normalize_datetime(query_end).isoformat(),
        "started_at": row["started_at"].isoformat(),
        "trace_id": row["trace_id"],
        "expires_at": expires_at.isoformat(),
    }
    encoded = base64.urlsafe_b64encode(json.dumps(payload, separators=(",", ":")).encode()).decode()
    signature = hmac.new(_cursor_key(settings), encoded.encode(), hashlib.sha256).hexdigest()
    return f"{encoded}.{signature}"


def _decode_cursor(
    settings: Settings,
    authorization: OperatorSessionAuthorization,
    cursor: str,
    status: str | None,
    query_start: datetime,
    query_end: datetime,
) -> tuple[datetime, str]:
    try:
        encoded, signature = cursor.split(".", 1)
        expected = hmac.new(_cursor_key(settings), encoded.encode(), hashlib.sha256).hexdigest()
        if not hmac.compare_digest(signature, expected):
            raise ValueError("signature")
        payload = json.loads(base64.urlsafe_b64decode(encoded.encode()))
        if payload["org_id"] != str(authorization.org_id):
            raise ValueError("tenant")
        if payload["query"] != _query_fingerprint(status, query_start, query_end):
            raise ValueError("query")
        expires_at = datetime.fromisoformat(payload["expires_at"])
        if expires_at <= datetime.now(UTC):
            raise ValueError("expired")
        return datetime.fromisoformat(payload["started_at"]), str(payload["trace_id"])
    except (ApiError, ValueError, KeyError, TypeError, json.JSONDecodeError, UnicodeError) as exc:
        raise ApiError(code=VALIDATION_ERROR, message="Invalid cursor") from exc


def cursor_query_bounds(
    settings: Settings,
    authorization: OperatorSessionAuthorization,
    cursor: str,
) -> tuple[datetime, datetime]:
    """Return the signed normalized bounds carried by a cursor."""
    try:
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
        return _normalize_datetime(datetime.fromisoformat(payload["query_start"])), _normalize_datetime(datetime.fromisoformat(payload["query_end"]))
    except (ApiError, ValueError, KeyError, TypeError, json.JSONDecodeError, UnicodeError) as exc:
        raise ApiError(code=VALIDATION_ERROR, message="Invalid cursor") from exc


def _duration_ms(started_at: datetime, ended_at: datetime | None) -> int | None:
    if ended_at is None:
        return None
    return max(0, round((ended_at - started_at).total_seconds() * 1000))


def _evidence(row: Any, observed_at: datetime) -> TraceEvidenceState:
    completeness = str(row["completeness"])
    freshness = "stale" if completeness == "late" else "unknown"
    return TraceEvidenceState(
        completeness=completeness,
        sample_decision=str(row["sample_decision"]),
        freshness=freshness,
        retention="unknown",
        source="postgres.evidence_runs",
        observed_at=observed_at,
    )


def _item(row: Any, observed_at: datetime) -> OperatorTraceListItem:
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
        evidence=_evidence(row, observed_at),
    )


def _validate_range(query_start: datetime, query_end: datetime) -> None:
    if query_start.tzinfo is None or query_end.tzinfo is None or query_end <= query_start:
        raise ApiError(code=VALIDATION_ERROR, message="Invalid trace time range")
    if query_end - query_start > _MAX_RANGE:
        raise ApiError(code=VALIDATION_ERROR, message="Trace time range exceeds maximum")


async def list_operator_traces(
    session: AsyncSession,
    settings: Settings,
    authorization: OperatorSessionAuthorization,
    *,
    query_start: datetime | None,
    query_end: datetime | None,
    status: str | None,
    limit: int,
    cursor: str | None,
) -> OperatorTraceListResponse:
    if limit < 1 or limit > _MAX_PAGE_SIZE:
        raise ApiError(code=VALIDATION_ERROR, message="Trace limit must be between 1 and 100")
    if cursor:
        cursor_start, cursor_end = cursor_query_bounds(settings, authorization, cursor)
        query_start = cursor_start if query_start is None else query_start
        query_end = cursor_end if query_end is None else query_end
    if query_end is None:
        query_end = datetime.now(UTC)
    if query_start is None:
        query_start = query_end - timedelta(hours=24)
    query_start = _normalize_datetime(query_start)
    query_end = _normalize_datetime(query_end)
    _validate_range(query_start, query_end)
    params: dict[str, object] = {
        "org_id": str(authorization.org_id),
        "query_start": query_start,
        "query_end": query_end,
        "limit": limit + 1,
    }
    has_cursor = bool(cursor)
    if cursor:
        cursor_started, cursor_trace = _decode_cursor(settings, authorization, cursor, status, query_start, query_end)
        params.update(cursor_started=cursor_started, cursor_trace=cursor_trace)
    if status:
        params["status"] = status
    if status and has_cursor:
        query = _LIST_STATUS_CURSOR_QUERY
    elif has_cursor:
        query = _LIST_CURSOR_QUERY
    elif status:
        query = _LIST_STATUS_QUERY
    else:
        query = _LIST_QUERY
    try:
        await session.execute(text("SET LOCAL statement_timeout = '3000ms'"))
        result = await session.execute(query, params)
        rows = list(result.mappings().all())
    except SQLAlchemyError as exc:
        raise ApiError(code=SERVICE_DEGRADED, message=_TRACE_UNAVAILABLE) from exc
    observed_at = datetime.now(UTC)
    truncated = len(rows) > limit
    rows = rows[:limit]
    next_cursor = _encode_cursor(settings, authorization, status, query_start, query_end, rows[-1]) if truncated else None
    return OperatorTraceListResponse(
        items=[_item(row, observed_at) for row in rows],
        next_cursor=next_cursor,
        truncated=truncated,
        observed_at=observed_at,
        query_start=query_start,
        query_end=query_end,
        limit=limit,
    )


async def get_operator_trace(
    session: AsyncSession,
    authorization: OperatorSessionAuthorization,
    *,
    trace_id: str,
) -> OperatorTraceDetailResponse:
    if not trace_id or len(trace_id) > 256:
        raise ApiError(code=NOT_FOUND, message=_TRACE_NOT_FOUND)
    query = _DETAIL_QUERY
    try:
        await session.execute(text("SET LOCAL statement_timeout = '3000ms'"))
        result = await session.execute(query, {"org_id": str(authorization.org_id), "query_start": datetime.min.replace(tzinfo=UTC), "query_end": datetime.max.replace(tzinfo=UTC), "trace_id": trace_id})
        row = result.mappings().first()
    except SQLAlchemyError as exc:
        raise ApiError(code=SERVICE_DEGRADED, message=_TRACE_UNAVAILABLE) from exc
    if row is None:
        raise ApiError(code=NOT_FOUND, message=_TRACE_NOT_FOUND)
    item = _item(row, datetime.now(UTC))
    return OperatorTraceDetailResponse(
        **item.model_dump(),
        unavailable_sections=("spans", "candidates", "score_explanation", "directives", "tools", "content"),
    )
