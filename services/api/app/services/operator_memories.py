"""Tenant-scoped, metadata-only operator memory reads."""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any
from uuid import UUID

from apierror_py import NOT_FOUND, VALIDATION_ERROR
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.errors import ApiError
from app.pagination import CursorPage, decode_cursor, encode_cursor, page_from_rows
from app.schemas.operator_memories import OperatorMemory

_MEMORY_NOT_FOUND_MSG = "Memory not found"

_MEMORY_COLUMNS = """
    m.id,
    m.agent_id,
    m.session_id,
    m.category,
    m.status,
    m.source,
    m.confidence,
    m.usefulness_score,
    m.content_tokens,
    m.retrieval_count,
    m.last_retrieved_at,
    m.pii_detected,
    m.pii_redacted,
    m.lifecycle_revision,
    m.tombstoned,
    m.expires_at,
    m.valid_from,
    m.valid_until,
    m.observed_at,
    m.created_at,
    m.updated_at,
    COALESCE(m.metadata->>'visibility', 'agent') AS visibility,
    COALESCE((m.metadata->>'pinned')::boolean, FALSE) AS pinned,
    COALESCE(m.metadata->'tags', '[]'::jsonb) AS tags
"""

_GET_MEMORY_SQL = f"""
    SELECT {_MEMORY_COLUMNS}
    FROM ibex_core.memories m
    WHERE m.id = CAST(:memory_id AS uuid)
      AND m.org_id = CAST(:org_id AS uuid)
"""

_LIST_MEMORIES_SQL = f"""
    SELECT {_MEMORY_COLUMNS}
    FROM ibex_core.memories m
    WHERE m.org_id = CAST(:org_id AS uuid)
      AND (
            CAST(:agent_id AS text) IS NULL
            OR m.agent_id = CAST(:agent_id AS uuid)
      )
      AND (
            CAST(:session_id AS text) IS NULL
            OR m.session_id = CAST(:session_id AS uuid)
      )
      AND (
            CAST(:status AS text) IS NULL
            OR m.status = CAST(:status AS text)
      )
      AND (
            CAST(:category AS text) IS NULL
            OR m.category = CAST(:category AS text)
      )
      AND (
            CAST(:cursor_created_at AS text) IS NULL
            OR m.created_at < CAST(:cursor_created_at AS timestamptz)
            OR (
                m.created_at = CAST(:cursor_created_at AS timestamptz)
                AND m.id < CAST(:cursor_id AS uuid)
            )
      )
    ORDER BY m.created_at DESC, m.id DESC
    LIMIT :limit
"""


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
    created_at: str | None
    memory_id: str | None


@dataclass(frozen=True)
class _FetchPageArgs:
    org_id: UUID
    filters: MemoryListFilters
    cursor: _MemoryListCursor
    limit: int


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
    created_at = payload.get("created_at")
    memory_id = payload.get("id")
    if not created_at or not memory_id:
        raise ApiError(code=VALIDATION_ERROR, message="Invalid cursor")
    return _MemoryListCursor(str(created_at), str(memory_id))


async def _fetch_memories_page(session: AsyncSession, args: _FetchPageArgs) -> list[Any]:
    params = {
        "org_id": str(args.org_id),
        "limit": args.limit + 1,
        "agent_id": str(args.filters.agent_id) if args.filters.agent_id else None,
        "session_id": str(args.filters.session_id) if args.filters.session_id else None,
        "status": args.filters.status,
        "category": args.filters.category,
        "cursor_created_at": args.cursor.created_at,
        "cursor_id": args.cursor.memory_id,
    }
    result = await session.execute(text(_LIST_MEMORIES_SQL), params)
    return list(result.mappings().all())


def _next_list_payload(memories: list[OperatorMemory], limit: int) -> dict[str, str] | None:
    if len(memories) <= limit:
        return None
    last = memories[limit - 1]
    return {"created_at": last.created_at.isoformat(), "id": str(last.id)}


async def list_operator_memories(
    session: AsyncSession, args: ListMemoriesArgs
) -> CursorPage[OperatorMemory]:
    list_cursor = _parse_list_cursor(args.cursor)
    rows = await _fetch_memories_page(
        session,
        _FetchPageArgs(
            org_id=args.org_id,
            filters=args.filters,
            cursor=list_cursor,
            limit=args.limit,
        ),
    )
    memories = [_memory_from_row(row) for row in rows]
    payload = _next_list_payload(memories, args.limit)
    next_cursor = encode_cursor(payload) if payload is not None else None
    return page_from_rows(memories, limit=args.limit, next_cursor=next_cursor)


async def get_operator_memory(
    session: AsyncSession, org_id: UUID, memory_id: UUID
) -> OperatorMemory:
    result = await session.execute(
        text(_GET_MEMORY_SQL),
        {"memory_id": str(memory_id), "org_id": str(org_id)},
    )
    row = result.mappings().first()
    if row is None:
        raise ApiError(code=NOT_FOUND, message=_MEMORY_NOT_FOUND_MSG)
    return _memory_from_row(row)
