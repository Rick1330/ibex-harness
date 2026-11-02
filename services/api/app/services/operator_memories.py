"""Tenant-scoped, metadata-only operator memory reads."""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any
from uuid import UUID

from apierror_py import NOT_FOUND
from sqlalchemy import and_, bindparam, column, literal_column, or_, select, table
from sqlalchemy.ext.asyncio import AsyncSession

from app.errors import ApiError
from app.pagination import CursorPage, encode_cursor, page_from_rows
from app.schemas.operator_memories import OperatorMemory
from app.services.operator_keyset import (
    KeysetCursor,
    keyset_cursor_payload,
    parse_keyset_cursor,
)
from app.services.operator_rows import row_value

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
    literal_column("""
        CASE
            WHEN memories.metadata->>'visibility' IN ('agent', 'org', 'session')
            THEN memories.metadata->>'visibility'
            ELSE 'agent'
        END
    """).label("visibility"),
    literal_column("""
        CASE
            WHEN jsonb_typeof(memories.metadata->'pinned') = 'boolean'
            THEN (memories.metadata->>'pinned')::boolean
            ELSE FALSE
        END
    """).label("pinned"),
    literal_column("""
        CASE
            WHEN jsonb_typeof(memories.metadata->'tags') = 'array'
            THEN memories.metadata->'tags'
            ELSE '[]'::jsonb
        END
    """).label("tags"),
)

_MEMORY_ORDER = (_MEMORIES.c.created_at.desc(), _MEMORIES.c.id.desc())
_FILTER_FIELDS = ("agent_id", "session_id", "status", "category")
_VISIBILITIES = frozenset({"agent", "org", "session"})
_MAX_TAGS = 32
_MAX_TAG_LENGTH = 64


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


def _tags_from_row(row: Any) -> list[str]:
    raw = row_value(row, "tags") or []
    if isinstance(raw, str):
        try:
            raw = json.loads(raw)
        except ValueError:
            return []
    if not isinstance(raw, list):
        return []
    tags = [tag for tag in raw if isinstance(tag, str) and tag]
    return [tag[:_MAX_TAG_LENGTH] for tag in tags[:_MAX_TAGS]]


def _visibility_from_row(row: Any) -> str:
    value = str(row_value(row, "visibility"))
    return value if value in _VISIBILITIES else "agent"


def _memory_from_row(row: Any) -> OperatorMemory:
    return OperatorMemory(
        id=row_value(row, "id"),
        agent_id=row_value(row, "agent_id"),
        session_id=row_value(row, "session_id"),
        category=row_value(row, "category"),
        status=row_value(row, "status"),
        source=row_value(row, "source"),
        confidence=float(row_value(row, "confidence")),
        usefulness_score=float(row_value(row, "usefulness_score")),
        content_tokens=int(row_value(row, "content_tokens")),
        retrieval_count=int(row_value(row, "retrieval_count")),
        last_retrieved_at=row_value(row, "last_retrieved_at"),
        pii_detected=bool(row_value(row, "pii_detected")),
        pii_redacted=bool(row_value(row, "pii_redacted")),
        visibility=_visibility_from_row(row),
        pinned=bool(row_value(row, "pinned")),
        tags=_tags_from_row(row),
        lifecycle_revision=int(row_value(row, "lifecycle_revision")),
        tombstoned=bool(row_value(row, "tombstoned")),
        expires_at=row_value(row, "expires_at"),
        valid_from=row_value(row, "valid_from"),
        valid_until=row_value(row, "valid_until"),
        observed_at=row_value(row, "observed_at"),
        created_at=row_value(row, "created_at"),
        updated_at=row_value(row, "updated_at"),
    )


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


def _list_statement(filters: MemoryListFilters, cursor: KeysetCursor) -> Any:
    clauses: list[Any] = [_MEMORIES.c.org_id == bindparam("org_id")]
    clauses.extend(
        _MEMORIES.c[field] == bindparam(field) for field in _active_filters(filters)
    )
    if cursor.created_at is not None and cursor.row_id is not None:
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
    cursor: KeysetCursor,
    limit: int,
) -> dict[str, Any]:
    params: dict[str, Any] = {"org_id": org_id, "limit": limit + 1}
    params.update(_active_filters(filters))
    if cursor.created_at is not None and cursor.row_id is not None:
        params["cursor_created_at"] = cursor.created_at
        params["cursor_id"] = cursor.row_id
    return params


async def list_operator_memories(
    session: AsyncSession, args: ListMemoriesArgs
) -> CursorPage[OperatorMemory]:
    list_cursor = parse_keyset_cursor(args.cursor)
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
    return keyset_cursor_payload(last.created_at, last.id)


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
