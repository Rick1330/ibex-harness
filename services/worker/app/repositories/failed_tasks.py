"""Dead-letter persistence for exhausted-retry Celery task failures."""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.db import session_as_service_account

_MAX_TRACEBACK_CHARS = 65_536

_INSERT_SQL = """
INSERT INTO ibex_core.failed_tasks (
    task_name,
    task_id,
    args,
    kwargs,
    exception_type,
    exception_message,
    traceback,
    retry_count,
    org_id
) VALUES (
    :task_name,
    :task_id,
    CAST(:args AS jsonb),
    CAST(:kwargs AS jsonb),
    :exception_type,
    :exception_message,
    :traceback,
    :retry_count,
    :org_id
)
ON CONFLICT (task_id) DO NOTHING
RETURNING id
"""


@dataclass(frozen=True, slots=True)
class FailedTaskRecord:
    """Row payload for ibex_core.failed_tasks inserts."""

    task_name: str
    task_id: str
    args: tuple[Any, ...] | list[Any]
    kwargs: dict[str, Any]
    exception_type: str
    exception_message: str
    traceback_text: str
    retry_count: int
    org_id: UUID | None


def _json_text(value: Any) -> str:
    return json.dumps(value, default=str)


def _truncate_traceback(traceback_text: str) -> str:
    if len(traceback_text) <= _MAX_TRACEBACK_CHARS:
        return traceback_text
    return traceback_text[:_MAX_TRACEBACK_CHARS] + "\n... [truncated]"


async def insert_failed_task(
    factory: async_sessionmaker[AsyncSession],
    record: FailedTaskRecord,
) -> bool:
    """Insert a dead-letter row. Returns False when task_id already exists."""
    params = {
        "task_name": record.task_name,
        "task_id": record.task_id,
        "args": _json_text(list(record.args)),
        "kwargs": _json_text(record.kwargs),
        "exception_type": record.exception_type,
        "exception_message": record.exception_message[:8192],
        "traceback": _truncate_traceback(record.traceback_text),
        "retry_count": record.retry_count,
        "org_id": str(record.org_id) if record.org_id else None,
    }
    async with session_as_service_account(factory) as session, session.begin_nested():
        result = await session.execute(
            text(_INSERT_SQL),  # nosemgrep: python.sqlalchemy.security.audit.avoid-sqlalchemy-text.avoid-sqlalchemy-text
            params,
        )
        inserted = result.first() is not None
    return inserted
