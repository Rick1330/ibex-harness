"""Tenant-scoped, metadata-only operator directive reads.

Two facts drive the contract, and they are deliberately separate:

- the **pointer**: `directives.active_version_id`, the version a *new* session
  would resolve to right now (Langfuse labels and OpenAI published prompt IDs
  work the same way — one mutable pointer at immutable versions);
- the **resolved history**: `sessions.directive_version_id`, the version each
  session actually used, pinned when the session started.

A rollback moves the pointer; it does not create a version. Version numbers are
monotonic and the version table is append-only (a trigger rejects UPDATE), so the
pointer may name an older version than the newest one.

Instruction text is never selected. `func.octet_length(content)` gives the stored
size without returning the content itself.

Every query filters `org_id` explicitly, including the joins and the
pointer-to-version lookup, because RLS is defense in depth, not the only guard.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import UUID

from apierror_py import NOT_FOUND
from sqlalchemy import and_, bindparam, column, func, or_, select, table
from sqlalchemy.ext.asyncio import AsyncSession

from app.errors import ApiError
from app.pagination import PaginationMeta, encode_cursor
from app.schemas.operator_directives import (
    OperatorDirectiveDetail,
    OperatorDirectivePage,
    OperatorDirectiveSummary,
    OperatorDirectiveUsage,
    OperatorDirectiveVersion,
)
from app.services.operator_keyset import (
    KeysetCursor,
    keyset_cursor_payload,
    parse_keyset_cursor,
)
from app.services.operator_rows import row_value

_USAGE_HOURS: dict[str, int] = {"24h": 24, "7d": 24 * 7, "30d": 24 * 30}
_DIGEST_PREFIX = 12
_DIRECTIVE_NOT_FOUND = "Directive not found"
# The newest N versions are returned, and the pointer target is always included
# even when it is older, so a rollback stays visible on a long history.
VERSIONS_LIMIT = 200
USAGE_LIMIT = 200

_DIRECTIVES = table(
    "directives",
    column("id"),
    column("org_id"),
    column("agent_id"),
    column("active_version_id"),
    column("injection_mode"),
    column("is_active"),
    column("created_at"),
    column("updated_at"),
    schema="ibex_core",
)

_VERSIONS = table(
    "directive_versions",
    column("id"),
    column("directive_id"),
    column("org_id"),
    column("version_num"),
    column("content"),
    column("content_hash"),
    column("created_by"),
    column("created_at"),
    schema="ibex_core",
)

_AGENTS = table(
    "agents",
    column("id"),
    column("org_id"),
    column("name"),
    column("slug"),
    schema="ibex_core",
)

_SESSIONS = table(
    "sessions",
    column("org_id"),
    column("directive_version_id"),
    column("created_at"),
    schema="ibex_core",
)


@dataclass(frozen=True)
class DirectiveListArgs:
    org_id: UUID
    state: str
    agent_id: UUID | None
    cursor: str | None
    limit: int


@dataclass(frozen=True)
class DirectiveDetailArgs:
    org_id: UUID
    directive_id: UUID
    usage_range: str


@dataclass(frozen=True)
class DirectiveHeader:
    id: UUID
    agent_id: UUID
    agent_name: str
    agent_slug: str
    is_active: bool
    injection_mode: str
    active_version_id: UUID | None
    updated_at: datetime


def usage_window(range_value: str, *, now: datetime | None = None) -> tuple[datetime, datetime]:
    end = now or datetime.now(UTC)
    return end - timedelta(hours=_USAGE_HOURS[range_value]), end


def _live_version_number() -> Any:
    """The version the pointer names, which may not be the newest after a rollback."""
    return (
        select(_VERSIONS.c.version_num)
        .where(
            _VERSIONS.c.id == _DIRECTIVES.c.active_version_id,
            _VERSIONS.c.org_id == _DIRECTIVES.c.org_id,
        )
        .scalar_subquery()
    )


def _cursor_clause(cursor: KeysetCursor) -> Any:
    return or_(
        _DIRECTIVES.c.updated_at < bindparam("cursor_updated_at"),
        and_(
            _DIRECTIVES.c.updated_at == bindparam("cursor_updated_at"),
            _DIRECTIVES.c.id < bindparam("cursor_id"),
        ),
    )


def _list_filter_clauses(args: DirectiveListArgs, cursor: KeysetCursor) -> list[Any]:
    clauses: list[Any] = [_DIRECTIVES.c.org_id == bindparam("org_id")]
    if args.state == "active":
        clauses.append(_DIRECTIVES.c.is_active.is_(True))
    elif args.state == "inactive":
        clauses.append(_DIRECTIVES.c.is_active.is_(False))
    if args.agent_id is not None:
        clauses.append(_DIRECTIVES.c.agent_id == bindparam("agent_id"))
    if cursor.created_at is not None and cursor.row_id is not None:
        clauses.append(_cursor_clause(cursor))
    return clauses


def _list_statement(args: DirectiveListArgs, cursor: KeysetCursor) -> Any:
    # Page the directives first, then aggregate versions for those ids only, so a
    # small page never groups the organization's whole version history.
    page = (
        select(_DIRECTIVES.c.id, _DIRECTIVES.c.updated_at)
        .select_from(_DIRECTIVES)
        .where(*_list_filter_clauses(args, cursor))
        .order_by(_DIRECTIVES.c.updated_at.desc(), _DIRECTIVES.c.id.desc())
        .limit(bindparam("limit"))
        .subquery("directive_page")
    )
    version_stats = (
        select(
            _VERSIONS.c.directive_id.label("directive_id"),
            func.count().label("version_count"),
            func.max(_VERSIONS.c.created_at).label("last_version_at"),
        )
        .select_from(_VERSIONS)
        .where(
            _VERSIONS.c.org_id == bindparam("org_id"),
            _VERSIONS.c.directive_id.in_(select(page.c.id)),
        )
        .group_by(_VERSIONS.c.directive_id)
        .subquery()
    )
    return (
        select(
            _DIRECTIVES.c.id,
            _DIRECTIVES.c.agent_id,
            _AGENTS.c.name.label("agent_name"),
            _AGENTS.c.slug.label("agent_slug"),
            _DIRECTIVES.c.is_active,
            _DIRECTIVES.c.injection_mode,
            _DIRECTIVES.c.updated_at,
            func.coalesce(version_stats.c.version_count, 0).label("version_count"),
            version_stats.c.last_version_at,
            _live_version_number().label("active_version_num"),
        )
        .select_from(
            page.join(_DIRECTIVES, _DIRECTIVES.c.id == page.c.id)
            .join(
                _AGENTS,
                and_(_AGENTS.c.id == _DIRECTIVES.c.agent_id, _AGENTS.c.org_id == _DIRECTIVES.c.org_id),
            )
            .outerjoin(version_stats, version_stats.c.directive_id == _DIRECTIVES.c.id)
        )
        .where(_DIRECTIVES.c.org_id == bindparam("org_id"))
        .order_by(_DIRECTIVES.c.updated_at.desc(), _DIRECTIVES.c.id.desc())
    )


def _summary_from_row(row: Any) -> OperatorDirectiveSummary:
    is_active = bool(row_value(row, "is_active"))
    live_version = row_value(row, "active_version_num")
    return OperatorDirectiveSummary(
        id=row_value(row, "id"),
        agent_id=row_value(row, "agent_id"),
        agent_name=row_value(row, "agent_name"),
        agent_slug=row_value(row, "agent_slug"),
        is_active=is_active,
        injection_mode=row_value(row, "injection_mode"),
        # An inactive directive serves nothing, whatever the pointer says.
        active_version_num=int(live_version) if is_active and live_version is not None else None,
        version_count=int(row_value(row, "version_count")),
        last_version_at=row_value(row, "last_version_at"),
        updated_at=row_value(row, "updated_at"),
    )


async def list_operator_directives(
    session: AsyncSession, args: DirectiveListArgs, *, now: datetime | None = None
) -> OperatorDirectivePage:
    cursor = parse_keyset_cursor(args.cursor)
    params: dict[str, Any] = {"org_id": args.org_id, "limit": args.limit + 1}
    if args.agent_id is not None:
        params["agent_id"] = args.agent_id
    if cursor.created_at is not None and cursor.row_id is not None:
        params["cursor_updated_at"] = cursor.created_at
        params["cursor_id"] = cursor.row_id
    result = await session.execute(_list_statement(args, cursor), params)
    rows = [_summary_from_row(row) for row in result.mappings().all()]
    has_more = len(rows) > args.limit
    data = rows[: args.limit]
    next_cursor = (
        encode_cursor(keyset_cursor_payload(data[-1].updated_at, data[-1].id))
        if has_more and data
        else None
    )
    observed = now or datetime.now(UTC)
    return OperatorDirectivePage(
        data=data,
        pagination=PaginationMeta(has_more=has_more, next_cursor=next_cursor),
        observed_at=observed,
    )


async def _fetch_header(session: AsyncSession, args: DirectiveDetailArgs) -> DirectiveHeader:
    statement = (
        select(
            _DIRECTIVES.c.id,
            _DIRECTIVES.c.agent_id,
            _AGENTS.c.name.label("agent_name"),
            _AGENTS.c.slug.label("agent_slug"),
            _DIRECTIVES.c.is_active,
            _DIRECTIVES.c.injection_mode,
            _DIRECTIVES.c.active_version_id,
            _DIRECTIVES.c.updated_at,
        )
        .select_from(
            _DIRECTIVES.join(
                _AGENTS,
                and_(_AGENTS.c.id == _DIRECTIVES.c.agent_id, _AGENTS.c.org_id == _DIRECTIVES.c.org_id),
            )
        )
        .where(
            _DIRECTIVES.c.org_id == bindparam("org_id"),
            _DIRECTIVES.c.id == bindparam("directive_id"),
        )
        .limit(1)
    )
    row = (
        await session.execute(statement, {"org_id": args.org_id, "directive_id": args.directive_id})
    ).mappings().first()
    if row is None:
        raise ApiError(code=NOT_FOUND, message=_DIRECTIVE_NOT_FOUND)
    return DirectiveHeader(
        id=row_value(row, "id"),
        agent_id=row_value(row, "agent_id"),
        agent_name=row_value(row, "agent_name"),
        agent_slug=row_value(row, "agent_slug"),
        is_active=bool(row_value(row, "is_active")),
        injection_mode=row_value(row, "injection_mode"),
        active_version_id=row_value(row, "active_version_id"),
        updated_at=row_value(row, "updated_at"),
    )


def _version_statement(pointed_only: bool) -> Any:
    statement = select(
        _VERSIONS.c.id,
        _VERSIONS.c.version_num,
        _VERSIONS.c.content_hash,
        func.octet_length(_VERSIONS.c.content).label("content_bytes"),
        _VERSIONS.c.created_by,
        _VERSIONS.c.created_at,
    ).select_from(_VERSIONS).where(
        _VERSIONS.c.org_id == bindparam("org_id"),
        _VERSIONS.c.directive_id == bindparam("directive_id"),
    )
    if pointed_only:
        return statement.where(_VERSIONS.c.id == bindparam("version_id"))
    return statement.order_by(_VERSIONS.c.version_num.desc()).limit(VERSIONS_LIMIT + 1)


async def _count_versions(session: AsyncSession, args: DirectiveDetailArgs) -> int:
    statement = (
        select(func.count())
        .select_from(_VERSIONS)
        .where(
            _VERSIONS.c.org_id == bindparam("org_id"),
            _VERSIONS.c.directive_id == bindparam("directive_id"),
        )
    )
    result = await session.execute(
        statement, {"org_id": args.org_id, "directive_id": args.directive_id}
    )
    return int(result.scalar_one())


async def _fetch_versions(
    session: AsyncSession, args: DirectiveDetailArgs, live_version_id: UUID | None
) -> tuple[list[Any], int]:
    rows = list(
        (
            await session.execute(
                _version_statement(pointed_only=False),
                {"org_id": args.org_id, "directive_id": args.directive_id},
            )
        ).mappings().all()
    )
    total = await _count_versions(session, args)
    rows = rows[:VERSIONS_LIMIT]
    if live_version_id is not None and not any(
        row_value(row, "id") == live_version_id for row in rows
    ):
        # A rollback can point at a version older than the newest page.
        extra = (
            await session.execute(
                _version_statement(pointed_only=True),
                {
                    "org_id": args.org_id,
                    "directive_id": args.directive_id,
                    "version_id": live_version_id,
                },
            )
        ).mappings().all()
        rows.extend(extra)
    rows.sort(key=lambda row: int(row_value(row, "version_num")), reverse=True)
    return rows, total


def _version_projection(
    rows: list[Any], live_version_id: UUID | None
) -> tuple[list[OperatorDirectiveVersion], dict[Any, int]]:
    number_by_id: dict[Any, int] = {}
    versions: list[OperatorDirectiveVersion] = []
    for row in rows:
        version_id = row_value(row, "id")
        version_num = int(row_value(row, "version_num"))
        number_by_id[version_id] = version_num
        versions.append(
            OperatorDirectiveVersion(
                version_num=version_num,
                content_digest=str(row_value(row, "content_hash"))[:_DIGEST_PREFIX],
                content_bytes=int(row_value(row, "content_bytes") or 0),
                created_by=row_value(row, "created_by"),
                created_at=row_value(row, "created_at"),
                is_live=live_version_id is not None and version_id == live_version_id,
            )
        )
    return versions, number_by_id


async def _fetch_usage(
    session: AsyncSession, args: DirectiveDetailArgs, window_start: datetime
) -> list[OperatorDirectiveUsage]:
    """Usage is independent of the version timeline limit.

    The join resolves the version number from `directive_versions` directly, so a
    session that ran on a version outside the newest 200 is still counted and
    still named. Only the table is capped, by session count.
    """
    directive_versions = (
        select(_VERSIONS.c.id, _VERSIONS.c.version_num)
        .where(
            _VERSIONS.c.org_id == bindparam("org_id"),
            _VERSIONS.c.directive_id == bindparam("directive_id"),
        )
        .subquery("directive_versions")
    )
    statement = (
        select(
            directive_versions.c.version_num,
            func.count().label("sessions"),
            func.max(_SESSIONS.c.created_at).label("last_session_at"),
        )
        .select_from(
            _SESSIONS.join(
                directive_versions,
                directive_versions.c.id == _SESSIONS.c.directive_version_id,
            )
        )
        .where(
            _SESSIONS.c.org_id == bindparam("org_id"),
            _SESSIONS.c.created_at >= bindparam("window_start"),
        )
        .group_by(directive_versions.c.version_num)
        .order_by(func.count().desc())
        .limit(USAGE_LIMIT + 1)
    )
    rows = (
        await session.execute(
            statement,
            {
                "org_id": args.org_id,
                "directive_id": args.directive_id,
                "window_start": window_start,
            },
        )
    ).mappings().all()
    usage = [
        OperatorDirectiveUsage(
            version_num=int(row_value(row, "version_num")),
            sessions=int(row_value(row, "sessions")),
            last_session_at=row_value(row, "last_session_at"),
        )
        for row in rows
    ]
    # The statement orders by count, but keep the projection deterministic if a
    # driver returns rows unordered.
    return sorted(usage, key=lambda item: item.sessions, reverse=True)


async def _count_usage_total(
    session: AsyncSession, args: DirectiveDetailArgs, window_start: datetime
) -> int:
    """Exact sessions in the window, independent of how many versions are listed."""
    statement = (
        select(func.count())
        .select_from(_SESSIONS)
        .where(
            _SESSIONS.c.org_id == bindparam("org_id"),
            _SESSIONS.c.directive_version_id.in_(
                select(_VERSIONS.c.id).where(
                    _VERSIONS.c.org_id == bindparam("org_id"),
                    _VERSIONS.c.directive_id == bindparam("directive_id"),
                )
            ),
            _SESSIONS.c.created_at >= bindparam("window_start"),
        )
    )
    result = await session.execute(
        statement,
        {
            "org_id": args.org_id,
            "directive_id": args.directive_id,
            "window_start": window_start,
        },
    )
    return int(result.scalar_one())


async def get_operator_directive(
    session: AsyncSession,
    args: DirectiveDetailArgs,
    *,
    now: datetime | None = None,
) -> OperatorDirectiveDetail:
    header = await _fetch_header(session, args)
    live_version_id = header.active_version_id if header.is_active else None
    version_rows, total_versions = await _fetch_versions(session, args, live_version_id)
    versions, number_by_id = _version_projection(version_rows, live_version_id)
    window_start, window_end = usage_window(args.usage_range, now=now)
    usage = await _fetch_usage(session, args, window_start)
    usage_total = await _count_usage_total(session, args, window_start)
    live_version_num = number_by_id.get(live_version_id) if live_version_id else None
    return OperatorDirectiveDetail(
        id=header.id,
        agent_id=header.agent_id,
        agent_name=header.agent_name,
        agent_slug=header.agent_slug,
        is_active=header.is_active,
        injection_mode=header.injection_mode,
        active_version_num=live_version_num,
        version_count=total_versions,
        last_version_at=versions[0].created_at if versions else None,
        updated_at=header.updated_at,
        versions=versions,
        versions_truncated=total_versions > len(versions),
        usage=usage[:USAGE_LIMIT],
        usage_truncated=len(usage) > USAGE_LIMIT,
        usage_total_sessions=usage_total,
        usage_range=args.usage_range,
        usage_window_start=window_start,
        observed_at=window_end,
        active_version_missing=live_version_id is not None and live_version_num is None,
    )
