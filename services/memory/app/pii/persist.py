"""Persist PII flags / status onto an existing memories row (org-scoped)."""

from __future__ import annotations

from dataclasses import dataclass
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.exceptions import StaleMemoryRevisionError
from app.lifecycle import (
    MemoryLifecycleEvent,
    enqueue_memory_lifecycle_event,
    lock_organization_for_memory_write,
)


@dataclass(frozen=True, slots=True)
class MemoryPiiUpdate:
    org_id: UUID
    memory_id: UUID
    content: str
    status: str
    pii_detected: bool
    pii_redacted: bool
    expected_revision: int


async def update_memory_pii_flags(
    factory: async_sessionmaker[AsyncSession],
    update: MemoryPiiUpdate,
) -> None:
    """Update content/status/PII flags with explicit org_id filter (defense in depth)."""
    async with factory() as session, session.begin():
        await lock_organization_for_memory_write(session, update.org_id)
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
                  AND tombstoned = FALSE
                  AND lifecycle_revision = :expected_revision
                RETURNING lifecycle_revision
                """
            ),
            {
                "content": update.content,
                "status": update.status,
                "pii_detected": update.pii_detected,
                "pii_redacted": update.pii_redacted,
                "memory_id": str(update.memory_id),
                "org_id": str(update.org_id),
                "expected_revision": update.expected_revision,
            },
        )
        if result.rowcount != 1:
            raise StaleMemoryRevisionError(
                "Memory is missing, tombstoned, or no longer at the expected lifecycle revision"
            )
        new_revision = int(result.scalar_one())
        if new_revision != update.expected_revision:
            await enqueue_memory_lifecycle_event(
                session,
                MemoryLifecycleEvent(
                    org_id=update.org_id,
                    memory_id=update.memory_id,
                    revision=new_revision,
                    event_type=("quarantined" if update.status == "quarantined" else "content_updated"),
                ),
            )
