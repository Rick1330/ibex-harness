"""Agent persistence, list filters, and lifecycle transitions."""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any, Literal
from uuid import UUID

from apierror_py import (
    AGENT_HAS_SESSIONS,
    AGENT_SLUG_CONFLICT,
    NOT_FOUND,
    VALIDATION_ERROR,
)
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.authz import AGENT_NOT_FOUND_MSG
from app.errors import ApiError
from app.pagination import CursorPage, decode_cursor, encode_cursor, page_from_rows
from app.schemas.agents import AgentCreate, AgentPatch, AgentResponse, AgentStatus

_AGENT_SLUG_UNIQUE = "agents_org_id_slug_key"

_GET_AGENT_SQL = """
    SELECT
        a.id,
        a.org_id,
        a.slug,
        a.name,
        a.description,
        a.status,
        a.default_provider,
        a.default_model,
        d.active_version_id AS active_directive_version_id,
        a.config,
        a.metadata,
        a.tags,
        a.total_sessions,
        a.total_memories,
        a.total_tokens_used,
        a.last_active_at,
        a.created_at,
        a.updated_at
    FROM ibex_core.agents a
    LEFT JOIN ibex_core.directives d
        ON d.agent_id = a.id AND d.org_id = a.org_id
    WHERE a.id = CAST(:agent_id AS uuid)
      AND a.org_id = CAST(:org_id AS uuid)
      AND a.deleted_at IS NULL
"""

_LIST_AGENTS_SQL = """
    SELECT
        a.id,
        a.org_id,
        a.slug,
        a.name,
        a.description,
        a.status,
        a.default_provider,
        a.default_model,
        d.active_version_id AS active_directive_version_id,
        a.config,
        a.metadata,
        a.tags,
        a.total_sessions,
        a.total_memories,
        a.total_tokens_used,
        a.last_active_at,
        a.created_at,
        a.updated_at
    FROM ibex_core.agents a
    LEFT JOIN ibex_core.directives d
        ON d.agent_id = a.id AND d.org_id = a.org_id
    WHERE a.org_id = CAST(:org_id AS uuid)
      AND a.deleted_at IS NULL
      AND (
            CAST(:status AS text) IS NULL
            OR a.status = CAST(:status AS text)
      )
      AND (
            CAST(:has_tags AS boolean) IS FALSE
            OR a.tags && ARRAY(
                SELECT jsonb_array_elements_text(CAST(:tags_json AS jsonb))
            )
      )
      AND (
            CAST(:search AS text) IS NULL
            OR a.name ILIKE CAST(:search AS text)
            OR a.slug ILIKE CAST(:search AS text)
      )
      AND (
            CAST(:cursor_created_at AS text) IS NULL
            OR a.created_at < CAST(:cursor_created_at AS timestamptz)
            OR (
                a.created_at = CAST(:cursor_created_at AS timestamptz)
                AND a.id < CAST(:cursor_id AS uuid)
            )
      )
    ORDER BY a.created_at DESC, a.id DESC
    LIMIT :limit
"""

_LOCK_AGENT_SQL = """
    SELECT id, total_sessions
    FROM ibex_core.agents
    WHERE id = CAST(:agent_id AS uuid)
      AND org_id = CAST(:org_id AS uuid)
      AND deleted_at IS NULL
    FOR UPDATE
"""

_SESSION_EXISTS_SQL = """
    SELECT EXISTS (
        SELECT 1
        FROM ibex_core.sessions
        WHERE agent_id = CAST(:agent_id AS uuid)
          AND org_id = CAST(:org_id AS uuid)
          AND deleted_at IS NULL
    )
"""

_SOFT_DELETE_SQL = """
    UPDATE ibex_core.agents
    SET deleted_at = NOW()
    WHERE id = CAST(:agent_id AS uuid)
      AND org_id = CAST(:org_id AS uuid)
      AND deleted_at IS NULL
    RETURNING id
"""

_PATCH_AGENT_SQL = """
    UPDATE ibex_core.agents
    SET
        name = CASE WHEN CAST(:set_name AS boolean)
            THEN :name ELSE name END,
        description = CASE WHEN CAST(:set_description AS boolean)
            THEN :description ELSE description END,
        config = CASE WHEN CAST(:set_config AS boolean)
            THEN CAST(:config AS jsonb) ELSE config END,
        metadata = CASE WHEN CAST(:set_metadata AS boolean)
            THEN CAST(:metadata AS jsonb) ELSE metadata END,
        tags = CASE WHEN CAST(:set_tags AS boolean)
            THEN ARRAY(SELECT jsonb_array_elements_text(CAST(:tags_json AS jsonb)))
            ELSE tags END,
        default_provider = CASE WHEN CAST(:set_default_provider AS boolean)
            THEN :default_provider ELSE default_provider END,
        default_model = CASE WHEN CAST(:set_default_model AS boolean)
            THEN :default_model ELSE default_model END
    WHERE id = CAST(:agent_id AS uuid)
      AND org_id = CAST(:org_id AS uuid)
      AND deleted_at IS NULL
    RETURNING id
"""

_STATUS_CAS_SQL = """
    UPDATE ibex_core.agents
    SET status = :new_status
    WHERE id = CAST(:agent_id AS uuid)
      AND org_id = CAST(:org_id AS uuid)
      AND deleted_at IS NULL
      AND status = :expected_status
    RETURNING id
"""

_CREATE_AGENT_SQL = """
    INSERT INTO ibex_core.agents (
        org_id, created_by, name, slug, description, config, metadata, tags,
        default_provider, default_model
    )
    VALUES (
        CAST(:org_id AS uuid),
        CAST(:created_by AS uuid),
        :name,
        :slug,
        :description,
        CAST(:config AS jsonb),
        CAST(:metadata AS jsonb),
        ARRAY(SELECT jsonb_array_elements_text(CAST(:tags_json AS jsonb))),
        :default_provider,
        :default_model
    )
    RETURNING id
"""

LifecycleAction = Literal["activate", "pause", "archive"]

_LIFECYCLE_NEXT: dict[LifecycleAction, dict[AgentStatus, AgentStatus]] = {
    "pause": {"active": "paused"},
    "activate": {
        "paused": "active",
        "archived": "active",
        "suspended": "active",
    },
    "archive": {
        "active": "archived",
        "paused": "archived",
        "suspended": "archived",
    },
}


@dataclass(frozen=True)
class AgentListFilters:
    status: AgentStatus | None = None
    tags: list[str] | None = None
    search: str | None = None


@dataclass(frozen=True)
class ListAgentsArgs:
    org_id: UUID
    cursor: str | None
    limit: int
    filters: AgentListFilters


@dataclass(frozen=True)
class _AgentListCursor:
    created_at: str | None
    agent_id: str | None


@dataclass(frozen=True)
class _FetchPageArgs:
    org_id: UUID
    filters: AgentListFilters
    cursor: _AgentListCursor
    limit: int


def _row_get(row: Any, key: str) -> Any:
    try:
        return row[key]
    except (KeyError, TypeError):
        return getattr(row, key)


def _agent_from_row(row: Any) -> AgentResponse:
    tags = _row_get(row, "tags") or []
    if not isinstance(tags, list):
        tags = list(tags)
    return AgentResponse(
        id=_row_get(row, "id"),
        org_id=_row_get(row, "org_id"),
        slug=_row_get(row, "slug"),
        name=_row_get(row, "name"),
        description=_row_get(row, "description"),
        status=_row_get(row, "status"),
        default_provider=_row_get(row, "default_provider"),
        default_model=_row_get(row, "default_model"),
        active_directive_version_id=_row_get(row, "active_directive_version_id"),
        config=_row_get(row, "config") or {},
        metadata=_row_get(row, "metadata") or {},
        tags=tags,
        total_sessions=int(_row_get(row, "total_sessions") or 0),
        total_memories=int(_row_get(row, "total_memories") or 0),
        total_tokens_used=int(_row_get(row, "total_tokens_used") or 0),
        last_active_at=_row_get(row, "last_active_at"),
        created_at=_row_get(row, "created_at"),
        updated_at=_row_get(row, "updated_at"),
    )


def _json_dumps(value: dict[str, Any]) -> str:
    return json.dumps(value, separators=(",", ":"))


def _tags_json(tags: list[str] | None) -> str:
    return json.dumps(tags or [])


def _parse_list_cursor(cursor: str | None) -> _AgentListCursor:
    try:
        payload = decode_cursor(cursor)
    except (TypeError, ValueError) as exc:
        raise ApiError(code=VALIDATION_ERROR, message="Invalid cursor") from exc
    if payload is None:
        return _AgentListCursor(None, None)
    created_at = payload.get("created_at")
    agent_id = payload.get("id")
    if not created_at or not agent_id:
        raise ApiError(code=VALIDATION_ERROR, message="Invalid cursor")
    return _AgentListCursor(str(created_at), str(agent_id))


def _constraint_name(exc: IntegrityError) -> str:
    orig = getattr(exc, "orig", None)
    name = getattr(orig, "constraint_name", None)
    if name:
        return str(name)
    diag = getattr(orig, "diag", None)
    if diag is not None:
        diag_name = getattr(diag, "constraint_name", None)
        if diag_name:
            return str(diag_name)
    return str(orig or exc)


def _is_slug_conflict(exc: IntegrityError) -> bool:
    name = _constraint_name(exc)
    return name == _AGENT_SLUG_UNIQUE or _AGENT_SLUG_UNIQUE in name


async def _fetch_agents_page(session: AsyncSession, args: _FetchPageArgs) -> list[Any]:
    tags = args.filters.tags or []
    search = f"%{args.filters.search}%" if args.filters.search else None
    params = {
        "org_id": str(args.org_id),
        "limit": args.limit + 1,
        "status": args.filters.status,
        "has_tags": bool(tags),
        "tags_json": _tags_json(tags),
        "search": search,
        "cursor_created_at": args.cursor.created_at,
        "cursor_id": args.cursor.agent_id,
    }
    result = await session.execute(text(_LIST_AGENTS_SQL), params)
    return list(result.mappings().all())


def _next_agent_list_payload(agents: list[AgentResponse], limit: int) -> dict[str, str] | None:
    if len(agents) <= limit:
        return None
    last = agents[limit - 1]
    return {"created_at": last.created_at.isoformat(), "id": str(last.id)}


async def list_agents(session: AsyncSession, args: ListAgentsArgs) -> CursorPage[AgentResponse]:
    list_cursor = _parse_list_cursor(args.cursor)
    rows = await _fetch_agents_page(
        session,
        _FetchPageArgs(
            org_id=args.org_id,
            filters=args.filters,
            cursor=list_cursor,
            limit=args.limit,
        ),
    )
    agents = [_agent_from_row(r) for r in rows]
    payload = _next_agent_list_payload(agents, args.limit)
    next_cursor = encode_cursor(payload) if payload is not None else None
    return page_from_rows(agents, limit=args.limit, next_cursor=next_cursor)


async def get_agent(session: AsyncSession, org_id: UUID, agent_id: UUID) -> AgentResponse:
    result = await session.execute(
        text(_GET_AGENT_SQL),
        {"agent_id": str(agent_id), "org_id": str(org_id)},
    )
    row = result.mappings().first()
    if row is None:
        raise ApiError(code=NOT_FOUND, message=AGENT_NOT_FOUND_MSG)
    return _agent_from_row(row)


@dataclass(frozen=True)
class CreateAgentArgs:
    org_id: UUID
    body: AgentCreate
    created_by: UUID | None


def _create_params(args: CreateAgentArgs) -> dict[str, Any]:
    body = args.body
    return {
        "org_id": str(args.org_id),
        "created_by": str(args.created_by) if args.created_by else None,
        "name": body.name,
        "slug": body.slug,
        "description": body.description,
        "config": _json_dumps(body.config or {}),
        "metadata": _json_dumps(body.metadata or {}),
        "tags_json": _tags_json(body.tags),
        "default_provider": body.default_provider,
        "default_model": body.default_model,
    }


def _api_error_from_create_integrity(exc: IntegrityError) -> ApiError:
    if _is_slug_conflict(exc):
        return ApiError(
            code=AGENT_SLUG_CONFLICT,
            message="An agent with this slug already exists in the organization",
        )
    return ApiError(
        code=VALIDATION_ERROR,
        message="Agent create failed validation constraints",
    )


async def create_agent(session: AsyncSession, args: CreateAgentArgs) -> AgentResponse:
    try:
        result = await session.execute(text(_CREATE_AGENT_SQL), _create_params(args))
        inserted = result.mappings().first()
        if inserted is None:
            raise ApiError(code=VALIDATION_ERROR, message="Unable to create agent")
        created = await get_agent(session, args.org_id, UUID(str(inserted["id"])))
        await session.commit()
    except IntegrityError as exc:
        await session.rollback()
        raise _api_error_from_create_integrity(exc) from exc
    return created


def _patch_flags(fields_set: set[str]) -> dict[str, bool]:
    return {
        "set_name": "name" in fields_set,
        "set_description": "description" in fields_set,
        "set_config": "config" in fields_set,
        "set_metadata": "metadata" in fields_set,
        "set_tags": "tags" in fields_set,
        "set_default_provider": "default_provider" in fields_set,
        "set_default_model": "default_model" in fields_set,
    }


async def patch_agent(
    session: AsyncSession,
    org_id: UUID,
    agent_id: UUID,
    patch: AgentPatch,
) -> AgentResponse:
    await get_agent(session, org_id, agent_id)
    fields_set = set(patch.model_fields_set)
    if not fields_set:
        return await get_agent(session, org_id, agent_id)

    flags = _patch_flags(fields_set)
    result = await session.execute(
        text(_PATCH_AGENT_SQL),
        {
            "agent_id": str(agent_id),
            "org_id": str(org_id),
            **flags,
            "name": patch.name,
            "description": patch.description,
            "config": _json_dumps(patch.config or {}),
            "metadata": _json_dumps(patch.metadata or {}),
            "tags_json": _tags_json(patch.tags),
            "default_provider": patch.default_provider,
            "default_model": patch.default_model,
        },
    )
    if result.mappings().first() is None:
        raise ApiError(code=NOT_FOUND, message=AGENT_NOT_FOUND_MSG)
    updated = await get_agent(session, org_id, agent_id)
    await session.commit()
    return updated


def _sessions_block_delete(*, live_sessions: bool, total_sessions: int) -> bool:
    return live_sessions or total_sessions > 0


async def _lock_agent_row(
    session: AsyncSession, ids: dict[str, str]
) -> Any:
    locked = await session.execute(text(_LOCK_AGENT_SQL), ids)
    row = locked.mappings().first()
    if row is None:
        raise ApiError(code=NOT_FOUND, message=AGENT_NOT_FOUND_MSG)
    return row


async def _live_sessions_exist(session: AsyncSession, ids: dict[str, str]) -> bool:
    result = await session.execute(text(_SESSION_EXISTS_SQL), ids)
    return bool(result.scalar())


async def soft_delete_agent(session: AsyncSession, org_id: UUID, agent_id: UUID) -> None:
    ids = {"agent_id": str(agent_id), "org_id": str(org_id)}
    row = await _lock_agent_row(session, ids)
    total = int(row["total_sessions"] or 0)
    if _sessions_block_delete(
        live_sessions=await _live_sessions_exist(session, ids),
        total_sessions=total,
    ):
        raise ApiError(
            code=AGENT_HAS_SESSIONS,
            message="Agent has session history; archive instead of delete",
        )

    result = await session.execute(text(_SOFT_DELETE_SQL), ids)
    if result.mappings().first() is None:
        raise ApiError(code=NOT_FOUND, message=AGENT_NOT_FOUND_MSG)
    await session.commit()


def _assert_lifecycle_transition(current: AgentStatus, action: LifecycleAction) -> AgentStatus:
    nxt = _LIFECYCLE_NEXT.get(action, {}).get(current)
    if nxt is None:
        raise ApiError(
            code=VALIDATION_ERROR,
            message=f"Cannot {action} agent in status '{current}'",
        )
    return nxt


async def set_agent_status(
    session: AsyncSession,
    org_id: UUID,
    agent_id: UUID,
    action: LifecycleAction,
) -> AgentResponse:
    current = await get_agent(session, org_id, agent_id)
    new_status = _assert_lifecycle_transition(current.status, action)
    result = await session.execute(
        text(_STATUS_CAS_SQL),
        {
            "agent_id": str(agent_id),
            "org_id": str(org_id),
            "new_status": new_status,
            "expected_status": current.status,
        },
    )
    if result.mappings().first() is None:
        raise ApiError(
            code=VALIDATION_ERROR,
            message="Agent status changed concurrently; retry the lifecycle transition",
        )
    updated = await get_agent(session, org_id, agent_id)
    await session.commit()
    return updated


async def activate_agent(session: AsyncSession, org_id: UUID, agent_id: UUID) -> AgentResponse:
    return await set_agent_status(session, org_id, agent_id, "activate")


async def pause_agent(session: AsyncSession, org_id: UUID, agent_id: UUID) -> AgentResponse:
    return await set_agent_status(session, org_id, agent_id, "pause")


async def archive_agent(session: AsyncSession, org_id: UUID, agent_id: UUID) -> AgentResponse:
    return await set_agent_status(session, org_id, agent_id, "archive")
