"""Optional org-scoped session lookup for last_extracted_turn.

Ordered after HTTP memory writes (not a shared cross-service transaction).
Idempotency and crash-window semantics: ADR-0065.
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


class PostgresSessionStore:
    """SELECT/UPDATE ibex_core.sessions with explicit org_id + RLS GUC."""

    def __init__(self, factory: async_sessionmaker[AsyncSession]) -> None:
        self._factory = factory

    def load(self, org_id: UUID, session_id: UUID) -> SessionSnapshot | None:
        return asyncio.run(self._load(org_id, session_id))

    def update_last_extracted_turn(
        self, org_id: UUID, session_id: UUID, last_extracted_turn: int
    ) -> None:
        asyncio.run(self._update(org_id, session_id, last_extracted_turn))

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
