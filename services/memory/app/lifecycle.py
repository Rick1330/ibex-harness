"""PostgreSQL memory lifecycle fencing and redacted outbox persistence."""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.exceptions import MemoryNotFoundError, StaleLifecycleError
from app.org_context import set_service_org


async def require_extraction_session(
    session: AsyncSession,
    *,
    org_id: UUID,
    agent_id: UUID,
    session_id: UUID | None,
    expected_revision: int | None,
) -> None:
    """Lock and verify source session in the memory-write transaction."""
    if session_id is None:
        if expected_revision is not None:
            raise StaleLifecycleError("session revision supplied without session_id")
        return
    if expected_revision is None or expected_revision < 1:
        raise StaleLifecycleError("expected session lifecycle revision is required")

    await set_service_org(session, org_id)
    row = (
        (
            await session.execute(
                text(
                    """
                SELECT agent_id, status, deleted_at, lifecycle_revision
                FROM ibex_core.sessions
                WHERE id = :session_id AND org_id = :org_id
                FOR UPDATE
                """
                ),
                {"session_id": str(session_id), "org_id": str(org_id)},
            )
        )
        .mappings()
        .one_or_none()
    )
    if (
        row is None
        or str(row["agent_id"]) != str(agent_id)
        or row["status"] != "completed"
        or row["deleted_at"] is not None
        or int(row["lifecycle_revision"]) != expected_revision
    ):
        raise StaleLifecycleError("source session lifecycle revision is stale or ineligible")


async def enqueue_memory_lifecycle_event(
    session: AsyncSession,
    *,
    org_id: UUID,
    memory_id: UUID,
    revision: int,
    event_type: str,
    occurred_at: datetime | None = None,
) -> None:
    """Persist only lifecycle identifiers/metadata in the caller's transaction."""
    if revision < 1:
        raise ValueError("memory lifecycle revision must be positive")
    if event_type not in {
        "created",
        "quarantined",
        "content_updated",
        "superseded",
        "forgotten",
        "expired",
        "purged",
    }:
        raise ValueError("unsupported memory lifecycle event type")
    await session.execute(
        text(
            """
            INSERT INTO ibex_core.memory_lifecycle_outbox (
                org_id, memory_id, revision, schema_version, event_type, occurred_at
            ) VALUES (
                :org_id, :memory_id, :revision, 1, :event_type, :occurred_at
            )
            """
        ),
        {
            "org_id": str(org_id),
            "memory_id": str(memory_id),
            "revision": revision,
            "event_type": event_type,
            "occurred_at": occurred_at or datetime.now(tz=UTC),
        },
    )


async def forget_memory_session(
    session: AsyncSession,
    *,
    org_id: UUID,
    agent_id: UUID,
    memory_id: UUID,
    expected_revision: int,
) -> int:
    """Tombstone one tenant/agent memory and enqueue its event atomically."""
    if expected_revision < 1:
        raise StaleLifecycleError("expected memory lifecycle revision must be positive")
    await set_service_org(session, org_id)
    row = (
        (
            await session.execute(
                text(
                    """
                SELECT lifecycle_revision, tombstoned
                FROM ibex_core.memories
                WHERE id = :memory_id AND org_id = :org_id AND agent_id = :agent_id
                FOR UPDATE
                """
                ),
                {
                    "memory_id": str(memory_id),
                    "org_id": str(org_id),
                    "agent_id": str(agent_id),
                },
            )
        )
        .mappings()
        .one_or_none()
    )
    if row is None:
        raise MemoryNotFoundError()
    current_revision = int(row["lifecycle_revision"])
    if bool(row["tombstoned"]) or current_revision != expected_revision:
        raise StaleLifecycleError("memory lifecycle revision is stale")

    result = await session.execute(
        text(
            """
            UPDATE ibex_core.memories
            SET status = 'deleted',
                deleted_at = COALESCE(deleted_at, NOW()),
                tombstoned = TRUE,
                embedding = NULL,
                embedding_model = NULL,
                embedding_dim = NULL,
                updated_at = NOW()
            WHERE id = :memory_id
              AND org_id = :org_id
              AND agent_id = :agent_id
              AND lifecycle_revision = :expected_revision
              AND tombstoned = FALSE
            RETURNING lifecycle_revision
            """
        ),
        {
            "memory_id": str(memory_id),
            "org_id": str(org_id),
            "agent_id": str(agent_id),
            "expected_revision": expected_revision,
        },
    )
    updated = result.mappings().one_or_none()
    if updated is None:
        raise StaleLifecycleError("memory lifecycle revision changed during forget")
    new_revision = int(updated["lifecycle_revision"])
    await enqueue_memory_lifecycle_event(
        session,
        org_id=org_id,
        memory_id=memory_id,
        revision=new_revision,
        event_type="forgotten",
    )
    return new_revision
