"""Tenant-scoped, metadata-only operator session reads."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any
from uuid import UUID

from apierror_py import NOT_FOUND
from sqlalchemy import and_, bindparam, column, or_, select, table, true
from sqlalchemy.ext.asyncio import AsyncSession

from app.errors import ApiError
from app.pagination import CursorPage, encode_cursor, page_from_rows
from app.schemas.operator_sessions import (
    MAX_SESSION_TURNS,
    OperatorSession,
    OperatorSessionDetail,
    OperatorSessionTurn,
    SessionTurnEvidence,
)
from app.services.operator_keyset import (
    KeysetCursor,
    keyset_cursor_payload,
    parse_keyset_cursor,
)
from app.services.operator_rows import row_value

_SESSION_NOT_FOUND_MSG = "Session not found"

_SESSIONS = table(
    "sessions",
    column("id"),
    column("org_id"),
    column("agent_id"),
    column("external_id"),
    column("status"),
    column("model"),
    column("provider"),
    column("directive_version_id"),
    column("turn_count"),
    column("total_input_tokens"),
    column("total_output_tokens"),
    column("total_latency_ms"),
    column("last_extracted_turn"),
    column("lifecycle_revision"),
    column("evidence_fence_version"),
    column("created_at"),
    column("updated_at"),
    column("completed_at"),
    column("deleted_at"),
    schema="ibex_core",
)

_CHECKPOINTS = table(
    "checkpoints",
    column("id"),
    column("org_id"),
    column("session_id"),
    column("turn_index"),
    column("request_id"),
    column("input_tokens"),
    column("output_tokens"),
    column("model"),
    column("provider"),
    column("latency_ms"),
    column("is_streaming"),
    column("is_complete"),
    column("created_at"),
    schema="ibex_core",
)

_EVIDENCE_RUNS = table(
    "evidence_runs",
    column("id"),
    column("org_id"),
    column("checkpoint_id"),
    column("trace_id"),
    column("completeness"),
    column("status"),
    column("error_code"),
    column("started_at"),
    column("ended_at"),
    schema="ibex_core",
)

_SESSION_PROJECTION = (
    _SESSIONS.c.id,
    _SESSIONS.c.agent_id,
    _SESSIONS.c.external_id,
    _SESSIONS.c.status,
    _SESSIONS.c.model,
    _SESSIONS.c.provider,
    _SESSIONS.c.directive_version_id,
    _SESSIONS.c.turn_count,
    _SESSIONS.c.total_input_tokens,
    _SESSIONS.c.total_output_tokens,
    _SESSIONS.c.total_latency_ms,
    _SESSIONS.c.last_extracted_turn,
    _SESSIONS.c.lifecycle_revision,
    _SESSIONS.c.evidence_fence_version,
    _SESSIONS.c.created_at,
    _SESSIONS.c.updated_at,
    _SESSIONS.c.completed_at,
)

_SESSION_ORDER = (_SESSIONS.c.created_at.desc(), _SESSIONS.c.id.desc())
_FILTER_FIELDS = ("agent_id", "status")

# One deterministic run per checkpoint: the latest started run, then the highest id.
_LATEST_RUN = (
    select(
        _EVIDENCE_RUNS.c.id.label("run_id"),
        _EVIDENCE_RUNS.c.trace_id,
        _EVIDENCE_RUNS.c.completeness,
        _EVIDENCE_RUNS.c.status,
        _EVIDENCE_RUNS.c.error_code,
        _EVIDENCE_RUNS.c.started_at,
        _EVIDENCE_RUNS.c.ended_at,
    )
    .where(
        _EVIDENCE_RUNS.c.org_id == bindparam("org_id"),
        _EVIDENCE_RUNS.c.checkpoint_id == _CHECKPOINTS.c.id,
    )
    .order_by(_EVIDENCE_RUNS.c.started_at.desc(), _EVIDENCE_RUNS.c.id.desc())
    .limit(1)
    .lateral("latest_run")
)

_TURN_PROJECTION = (
    _CHECKPOINTS.c.id,
    _CHECKPOINTS.c.turn_index,
    _CHECKPOINTS.c.request_id,
    _CHECKPOINTS.c.input_tokens,
    _CHECKPOINTS.c.output_tokens,
    _CHECKPOINTS.c.model,
    _CHECKPOINTS.c.provider,
    _CHECKPOINTS.c.latency_ms,
    _CHECKPOINTS.c.is_streaming,
    _CHECKPOINTS.c.is_complete,
    _CHECKPOINTS.c.created_at,
    _LATEST_RUN.c.run_id,
    _LATEST_RUN.c.trace_id,
    _LATEST_RUN.c.completeness,
    _LATEST_RUN.c.status,
    _LATEST_RUN.c.error_code,
    _LATEST_RUN.c.started_at,
    _LATEST_RUN.c.ended_at,
)


@dataclass(frozen=True)
class SessionListFilters:
    agent_id: UUID | None = None
    status: str | None = None


@dataclass(frozen=True)
class ListSessionsArgs:
    org_id: UUID
    cursor: str | None
    limit: int
    filters: SessionListFilters


def _session_from_row(row: Any) -> OperatorSession:
    return OperatorSession(
        id=row_value(row, "id"),
        agent_id=row_value(row, "agent_id"),
        external_id=row_value(row, "external_id"),
        status=row_value(row, "status"),
        model=row_value(row, "model"),
        provider=row_value(row, "provider"),
        directive_version_id=row_value(row, "directive_version_id"),
        turn_count=int(row_value(row, "turn_count")),
        total_input_tokens=int(row_value(row, "total_input_tokens")),
        total_output_tokens=int(row_value(row, "total_output_tokens")),
        total_latency_ms=int(row_value(row, "total_latency_ms")),
        last_extracted_turn=int(row_value(row, "last_extracted_turn")),
        lifecycle_revision=int(row_value(row, "lifecycle_revision")),
        evidence_fence_version=int(row_value(row, "evidence_fence_version")),
        created_at=row_value(row, "created_at"),
        updated_at=row_value(row, "updated_at"),
        completed_at=row_value(row, "completed_at"),
    )


def _evidence_status(value: Any) -> str:
    return "ok" if str(value) == "ok" else "error"


def _turn_from_row(row: Any) -> OperatorSessionTurn:
    run_id = row_value(row, "run_id")
    trace = None
    if run_id is not None:
        trace = SessionTurnEvidence(
            run_id=run_id,
            trace_id=str(row_value(row, "trace_id")),
            completeness=row_value(row, "completeness"),
            status=_evidence_status(row_value(row, "status")),
            error_code=row_value(row, "error_code"),
            started_at=row_value(row, "started_at"),
            ended_at=row_value(row, "ended_at"),
        )
    return OperatorSessionTurn(
        id=row_value(row, "id"),
        turn_index=int(row_value(row, "turn_index")),
        request_id=str(row_value(row, "request_id")),
        input_tokens=int(row_value(row, "input_tokens")),
        output_tokens=int(row_value(row, "output_tokens")),
        model=str(row_value(row, "model")),
        provider=str(row_value(row, "provider")),
        latency_ms=int(row_value(row, "latency_ms")),
        is_streaming=bool(row_value(row, "is_streaming")),
        is_complete=bool(row_value(row, "is_complete")),
        created_at=row_value(row, "created_at"),
        trace=trace,
    )


def _active_filters(filters: SessionListFilters) -> dict[str, Any]:
    values = {field: getattr(filters, field) for field in _FILTER_FIELDS}
    return {field: value for field, value in values.items() if value is not None}


def _list_statement(filters: SessionListFilters, cursor: KeysetCursor) -> Any:
    clauses: list[Any] = [
        _SESSIONS.c.org_id == bindparam("org_id"),
        _SESSIONS.c.deleted_at.is_(None),
    ]
    clauses.extend(
        _SESSIONS.c[field] == bindparam(field) for field in _active_filters(filters)
    )
    if cursor.created_at is not None and cursor.row_id is not None:
        clauses.append(_cursor_clause())
    return (
        select(*_SESSION_PROJECTION)
        .select_from(_SESSIONS)
        .where(*clauses)
        .order_by(*_SESSION_ORDER)
        .limit(bindparam("limit"))
    )


def _cursor_clause() -> Any:
    return or_(
        _SESSIONS.c.created_at < bindparam("cursor_created_at"),
        and_(
            _SESSIONS.c.created_at == bindparam("cursor_created_at"),
            _SESSIONS.c.id < bindparam("cursor_id"),
        ),
    )


def _list_params(
    org_id: UUID,
    filters: SessionListFilters,
    cursor: KeysetCursor,
    limit: int,
) -> dict[str, Any]:
    params: dict[str, Any] = {"org_id": org_id, "limit": limit + 1}
    params.update(_active_filters(filters))
    if cursor.created_at is not None and cursor.row_id is not None:
        params["cursor_created_at"] = cursor.created_at
        params["cursor_id"] = cursor.row_id
    return params


def _next_list_payload(
    sessions: list[OperatorSession], limit: int
) -> dict[str, str] | None:
    if len(sessions) <= limit:
        return None
    last = sessions[limit - 1]
    return keyset_cursor_payload(last.created_at, last.id)


async def list_operator_sessions(
    session: AsyncSession, args: ListSessionsArgs
) -> CursorPage[OperatorSession]:
    list_cursor = parse_keyset_cursor(args.cursor)
    result = await session.execute(
        _list_statement(args.filters, list_cursor),
        _list_params(args.org_id, args.filters, list_cursor, args.limit),
    )
    sessions = [_session_from_row(row) for row in result.mappings().all()]
    payload = _next_list_payload(sessions, args.limit)
    next_cursor = encode_cursor(payload) if payload is not None else None
    return page_from_rows(sessions, limit=args.limit, next_cursor=next_cursor)


def _session_statement() -> Any:
    return (
        select(*_SESSION_PROJECTION)
        .select_from(_SESSIONS)
        .where(
            _SESSIONS.c.org_id == bindparam("org_id"),
            _SESSIONS.c.id == bindparam("session_id"),
            _SESSIONS.c.deleted_at.is_(None),
        )
        .limit(1)
    )


def _turn_statement() -> Any:
    return (
        select(*_TURN_PROJECTION)
        .select_from(_CHECKPOINTS.outerjoin(_LATEST_RUN, true()))
        .where(
            _CHECKPOINTS.c.org_id == bindparam("org_id"),
            _CHECKPOINTS.c.session_id == bindparam("session_id"),
        )
        .order_by(_CHECKPOINTS.c.turn_index.asc())
        .limit(MAX_SESSION_TURNS + 1)
    )


async def get_operator_session(
    session: AsyncSession, org_id: UUID, session_id: UUID
) -> OperatorSessionDetail:
    result = await session.execute(
        _session_statement(), {"org_id": org_id, "session_id": session_id}
    )
    row = result.mappings().first()
    if row is None:
        raise ApiError(code=NOT_FOUND, message=_SESSION_NOT_FOUND_MSG)
    record = _session_from_row(row)

    turns_result = await session.execute(
        _turn_statement(), {"org_id": org_id, "session_id": session_id}
    )
    turns = [_turn_from_row(turn) for turn in turns_result.mappings().all()]
    truncated = len(turns) > MAX_SESSION_TURNS
    return OperatorSessionDetail(
        **record.model_dump(),
        turns=turns[:MAX_SESSION_TURNS],
        turns_truncated=truncated,
    )
