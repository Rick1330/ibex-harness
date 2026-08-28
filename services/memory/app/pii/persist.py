"""Persist PII flags / status onto an existing memories row (org-scoped)."""

from __future__ import annotations

from dataclasses import dataclass
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.org_context import set_service_org


@dataclass(frozen=True, slots=True)
class MemoryPiiUpdate:
    org_id: UUID
    memory_id: UUID
    content: str
    status: str
    pii_detected: bool
    pii_redacted: bool


async def update_memory_pii_flags(
    factory: async_sessionmaker[AsyncSession],
    update: MemoryPiiUpdate,
) -> None:
    """Update content/status/PII flags with explicit org_id filter (defense in depth)."""
    async with factory() as session, session.begin():
        await set_service_org(session, update.org_id)
        result = await session.execute(
            text(  # nosemgrep: python.sqlalchemy.security.audit.avoid-sqlalchemy-text.avoid-sqlalchemy-text
                """
                UPDATE ibex_core.memories
                SET content = :content,
                    status = :status,
                    pii_detected = :pii_detected,
                    pii_redacted = :pii_redacted,
                    updated_at = NOW()
                WHERE id = :memory_id
                  AND org_id = :org_id
                  AND deleted_at IS NULL
                """
            ),
            {
                "content": update.content,
                "status": update.status,
                "pii_detected": update.pii_detected,
                "pii_redacted": update.pii_redacted,
                "memory_id": str(update.memory_id),
                "org_id": str(update.org_id),
            },
        )
        if result.rowcount != 1:
            msg = f"memory update expected 1 row, got {result.rowcount}"
            raise RuntimeError(msg)
