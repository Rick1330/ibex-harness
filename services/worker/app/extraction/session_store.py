"""Org-scoped session lookup for last_extracted_turn (mandatory for extraction).

Pointer advances after each completed turn's HTTP writes (ADR-0065). Still not
a shared cross-service transaction with services/memory.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from datetime import datetime
from typing import Protocol
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker


@dataclass(frozen=True, slots=True)
class SessionSnapshot:
    last_extracted_turn: int
    status: str
    deleted_at: datetime | None


class SessionStore(Protocol):
    def load(self, org_id: UUID, session_id: UUID) -> SessionSnapshot | None: ...

    def update_last_extracted_turn(
        self, org_id: UUID, session_id: UUID, last_extracted_turn: int
    ) -> None: ...


def _run_coro(coro: object) -> object:
    """Run *coro* on the worker process loop when set (Celery prefork).

    ``asyncio.run`` creates a new loop and breaks SQLAlchemy async engines
    initialized in ``worker_process_init`` (attached to ``_worker_loop``).
    """
    try:
        loop = asyncio.get_event_loop()
    except RuntimeError:
        return asyncio.run(coro)  # type: ignore[arg-type]
    if loop.is_closed():
        return asyncio.run(coro)  # type: ignore[arg-type]
    if loop.is_running():
        # Nested call inside an already-running loop — unexpected for Celery tasks.
        return asyncio.run_coroutine_threadsafe(coro, loop).result()  # type: ignore[arg-type]
    return loop.run_until_complete(coro)  # type: ignore[arg-type]


class PostgresSessionStore:
    """SELECT/UPDATE ibex_core.sessions with explicit org_id + RLS GUC."""

    def __init__(self, factory: async_sessionmaker[AsyncSession]) -> None:
        self._factory = factory

    def load(self, org_id: UUID, session_id: UUID) -> SessionSnapshot | None:
        return _run_coro(self._load(org_id, session_id))  # type: ignore[return-value]

    def update_last_extracted_turn(
        self, org_id: UUID, session_id: UUID, last_extracted_turn: int
    ) -> None:
        _run_coro(self._update(org_id, session_id, last_extracted_turn))

    async def _load(self, org_id: UUID, session_id: UUID) -> SessionSnapshot | None:
        async with self._factory() as session, session.begin():
            await _set_org_guc(session, org_id)
            result = await session.execute(
                text(  # nosemgrep: python.sqlalchemy.security.audit.avoid-sqlalchemy-text.avoid-sqlalchemy-text
                    """
                    SELECT last_extracted_turn, status, deleted_at
                    FROM ibex_core.sessions
                    WHERE id = :session_id AND org_id = :org_id
                    """
                ),
                {"session_id": session_id, "org_id": org_id},
            )
            row = result.one_or_none()
        if row is None:
            return None
        return SessionSnapshot(
            last_extracted_turn=int(row.last_extracted_turn),
            status=str(row.status),
            deleted_at=row.deleted_at,
        )

    async def _update(
        self, org_id: UUID, session_id: UUID, last_extracted_turn: int
    ) -> None:
        async with self._factory() as session, session.begin():
            await _set_org_guc(session, org_id)
            await session.execute(
                text(  # nosemgrep: python.sqlalchemy.security.audit.avoid-sqlalchemy-text.avoid-sqlalchemy-text
                    """
                    UPDATE ibex_core.sessions
                    SET last_extracted_turn = GREATEST(last_extracted_turn, :turn)
                    WHERE id = :session_id AND org_id = :org_id
                    """
                ),
                {
                    "turn": last_extracted_turn,
                    "session_id": session_id,
                    "org_id": org_id,
                },
            )


async def _set_org_guc(session: AsyncSession, org_id: UUID) -> None:
    await session.execute(
        text(  # nosemgrep: python.sqlalchemy.security.audit.avoid-sqlalchemy-text.avoid-sqlalchemy-text
            "SELECT set_config('app.current_org_id', :org_id, true)"
        ),
        {"org_id": str(org_id)},
    )
