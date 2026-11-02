"""Tenant-scoped, metadata-only operator memory reads."""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime
from typing import Any
from uuid import UUID

from apierror_py import NOT_FOUND, VALIDATION_ERROR
from sqlalchemy import and_, bindparam, column, literal_column, or_, select, table
from sqlalchemy.ext.asyncio import AsyncSession

from app.errors import ApiError
from app.pagination import CursorPage, decode_cursor, encode_cursor, page_from_rows
from app.schemas.operator_memories import OperatorMemory

_MEMORY_NOT_FOUND_MSG = "Memory not found"

_MEMORIES = table(
    "memories",
    column("id"),
    column("agent_id"),
    column("session_id"),
    column("category"),
    column("status"),
    column("source"),
    column("confidence"),
    column("usefulness_score"),
    column("content_tokens"),
    column("retrieval_count"),
    column("last_retrieved_at"),
    column("pii_detected"),
    column("pii_redacted"),
    column("lifecycle_revision"),
    column("tombstoned"),
    column("expires_at"),
    column("valid_from"),
    column("valid_until"),
    column("observed_at"),
    column("created_at"),
    column("updated_at"),
    column("metadata"),
    column("org_id"),
    schema="ibex_core",
)

# One projection shared by the list and detail reads. The raw ``metadata``
# column is never selected; only the three presentation fields are projected.
_MEMORY_PROJECTION = (
    _MEMORIES.c.id,
    _MEMORIES.c.agent_id,
    _MEMORIES.c.session_id,
    _MEMORIES.c.category,
    _MEMORIES.c.status,
    _MEMORIES.c.source,
    _MEMORIES.c.confidence,
    _MEMORIES.c.usefulness_score,
    _MEMORIES.c.content_tokens,
    _MEMORIES.c.retrieval_count,
    _MEMORIES.c.last_retrieved_at,
    _MEMORIES.c.pii_detected,
    _MEMORIES.c.pii_redacted,
    _MEMORIES.c.lifecycle_revision,
    _MEMORIES.c.tombstoned,
    _MEMORIES.c.expires_at,
    _MEMORIES.c.valid_from,
    _MEMORIES.c.valid_until,
    _MEMORIES.c.observed_at,
    _MEMORIES.c.created_at,
    _MEMORIES.c.updated_at,
    literal_column("COALESCE(memories.metadata->>'visibility', 'agent')").label("visibility"),
    literal_column("COALESCE((memories.metadata->>'pinned')::boolean, FALSE)").label("pinned"),
    literal_column("COALESCE(memories.metadata->'tags', '[]'::jsonb)").label("tags"),
)

_MEMORY_ORDER = (_MEMORIES.c.created_at.desc(), _MEMORIES.c.id.desc())
_FILTER_FIELDS = ("agent_id", "session_id", "status", "category")


@dataclass(frozen=True)
class MemoryListFilters:
    agent_id: UUID | None = None
    session_id: UUID | None = None
    status: str | None = None
    category: str | None = None


@dataclass(frozen=True)
class ListMemoriesArgs:
    org_id: UUID
    cursor: str | None
    limit: int
    filters: MemoryListFilters


@dataclass(frozen=True)
class _MemoryListCursor:
    created_at: datetime | None
    memory_id: UUID | None


def _row_get(row: Any, key: str) -> Any:
    try:
        return row[key]
    except (KeyError, TypeError):
        return getattr(row, key)


def _tags_from_row(row: Any) -> list[str]:
    raw = _row_get(row, "tags") or []
    if isinstance(raw, str):
        raw = json.loads(raw)
    if not isinstance(raw, list):
        return []
    return [str(tag) for tag in raw if isinstance(tag, str) and tag]


def _memory_from_row(row: Any) -> OperatorMemory:
    return OperatorMemory(
        id=_row_get(row, "id"),
        agent_id=_row_get(row, "agent_id"),
        session_id=_row_get(row, "session_id"),
        category=_row_get(row, "category"),
        status=_row_get(row, "status"),
        source=_row_get(row, "source"),
        confidence=float(_row_get(row, "confidence")),
        usefulness_score=float(_row_get(row, "usefulness_score")),
        content_tokens=int(_row_get(row, "content_tokens")),
        retrieval_count=int(_row_get(row, "retrieval_count")),
        last_retrieved_at=_row_get(row, "last_retrieved_at"),
        pii_detected=bool(_row_get(row, "pii_detected")),
        pii_redacted=bool(_row_get(row, "pii_redacted")),
        visibility=str(_row_get(row, "visibility")),
        pinned=bool(_row_get(row, "pinned")),
        tags=_tags_from_row(row),
        lifecycle_revision=int(_row_get(row, "lifecycle_revision")),
        tombstoned=bool(_row_get(row, "tombstoned")),
        expires_at=_row_get(row, "expires_at"),
        valid_from=_row_get(row, "valid_from"),
        valid_until=_row_get(row, "valid_until"),
        observed_at=_row_get(row, "observed_at"),
        created_at=_row_get(row, "created_at"),
        updated_at=_row_get(row, "updated_at"),
    )


def _parse_list_cursor(cursor: str | None) -> _MemoryListCursor:
    try:
        payload = decode_cursor(cursor)
    except (TypeError, ValueError) as exc:
        raise ApiError(code=VALIDATION_ERROR, message="Invalid cursor") from exc
    if payload is None:
        return _MemoryListCursor(None, None)
    try:
        created_at = datetime.fromisoformat(str(payload["created_at"]))
        memory_id = UUID(str(payload["id"]))
    except (KeyError, TypeError, ValueError) as exc:
        raise ApiError(code=VALIDATION_ERROR, message="Invalid cursor") from exc
    return _MemoryListCursor(created_at, memory_id)


def _active_filters(filters: MemoryListFilters) -> dict[str, Any]:
    values = {field: getattr(filters, field) for field in _FILTER_FIELDS}
    return {field: value for field, value in values.items() if value is not None}


def _cursor_clause() -> Any:
    return or_(
        _MEMORIES.c.created_at < bindparam("cursor_created_at"),
        and_(
            _MEMORIES.c.created_at == bindparam("cursor_created_at"),
            _MEMORIES.c.id < bindparam("cursor_id"),
        ),
    )


def _list_statement(filters: MemoryListFilters, cursor: _MemoryListCursor) -> Any:
    clauses: list[Any] = [_MEMORIES.c.org_id == bindparam("org_id")]
    clauses.extend(
        _MEMORIES.c[field] == bindparam(field) for field in _active_filters(filters)
    )
    if cursor.created_at is not None and cursor.memory_id is not None:
        clauses.append(_cursor_clause())
    return (
        select(*_MEMORY_PROJECTION)
        .select_from(_MEMORIES)
        .where(*clauses)
        .order_by(*_MEMORY_ORDER)
        .limit(bindparam("limit"))
    )


def _list_params(
    org_id: UUID,
    filters: MemoryListFilters,
    cursor: _MemoryListCursor,
    limit: int,
) -> dict[str, Any]:
    params: dict[str, Any] = {"org_id": org_id, "limit": limit + 1}
    params.update(_active_filters(filters))
    if cursor.created_at is not None and cursor.memory_id is not None:
        params["cursor_created_at"] = cursor.created_at
        params["cursor_id"] = cursor.memory_id
    return params


async def list_operator_memories(
    session: AsyncSession, args: ListMemoriesArgs
) -> CursorPage[OperatorMemory]:
    list_cursor = _parse_list_cursor(args.cursor)
    result = await session.execute(
        _list_statement(args.filters, list_cursor),
        _list_params(args.org_id, args.filters, list_cursor, args.limit),
    )
    memories = [_memory_from_row(row) for row in result.mappings().all()]
    payload = _next_list_payload(memories, args.limit)
    next_cursor = encode_cursor(payload) if payload is not None else None
    return page_from_rows(memories, limit=args.limit, next_cursor=next_cursor)


def _next_list_payload(memories: list[OperatorMemory], limit: int) -> dict[str, str] | None:
    if len(memories) <= limit:
        return None
    last = memories[limit - 1]
    return {"created_at": last.created_at.isoformat(), "id": str(last.id)}


async def get_operator_memory(
    session: AsyncSession, org_id: UUID, memory_id: UUID
) -> OperatorMemory:
    statement = (
        select(*_MEMORY_PROJECTION)
        .select_from(_MEMORIES)
        .where(
            _MEMORIES.c.org_id == bindparam("org_id"),
            _MEMORIES.c.id == bindparam("memory_id"),
        )
        .limit(1)
    )
    result = await session.execute(statement, {"org_id": org_id, "memory_id": memory_id})
    row = result.mappings().first()
    if row is None:
        raise ApiError(code=NOT_FOUND, message=_MEMORY_NOT_FOUND_MSG)
    return _memory_from_row(row)
