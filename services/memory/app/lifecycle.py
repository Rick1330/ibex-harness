"""PostgreSQL memory lifecycle fencing and redacted outbox persistence."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.exceptions import (
    MemoryNotFoundError,
    MemoryOrganizationUnavailableError,
    StaleLifecycleError,
)
from app.org_context import set_service_org


@dataclass(frozen=True, slots=True)
class ExtractionSessionFence:
    """Expected source-session state for one extraction memory write."""

    org_id: UUID
    agent_id: UUID
    session_id: UUID | None
    expected_revision: int | None


@dataclass(frozen=True, slots=True)
class MemoryLifecycleEvent:
    """Redacted event metadata persisted with the corresponding mutation."""

    org_id: UUID
    memory_id: UUID
    revision: int
    event_type: str
    occurred_at: datetime | None = None


@dataclass(frozen=True, slots=True)
class ForgetMemory:
    """Tenant-scoped forget request with its expected memory revision."""

    org_id: UUID
    agent_id: UUID
    memory_id: UUID
    expected_revision: int


_EVENT_TYPES = frozenset(
    {
        "created",
        "quarantined",
        "content_updated",
        "superseded",
        "forgotten",
        "expired",
        "purged",
    }
)


async def lock_organization_for_memory_write(
    session: AsyncSession, org_id: UUID
) -> None:
    """Serialize memory mutations against org purge and reject cancelled orgs."""
    await set_service_org(session, org_id)
    await session.execute(
        text(
            "SELECT pg_advisory_xact_lock_shared(hashtext(CAST(:org_id AS text)))"
        ),
        {"org_id": str(org_id)},
    )
    row = (
        await session.execute(
            text(
                """
                SELECT status, deleted_at
                FROM ibex_core.organizations
                WHERE id = :org_id
                FOR SHARE
                """
            ),
            {"org_id": str(org_id)},
        )
    ).mappings().one_or_none()
    if row is None or row["status"] == "cancelled" or row["deleted_at"] is not None:
        raise MemoryOrganizationUnavailableError()


async def require_extraction_session(
    session: AsyncSession, fence: ExtractionSessionFence
) -> None:
    """Lock and verify the source session in the memory-write transaction."""
    if fence.session_id is None:
        if fence.expected_revision is not None:
            raise StaleLifecycleError("session revision supplied without session_id")
        return
    if fence.expected_revision is None or fence.expected_revision < 1:
        raise StaleLifecycleError("expected session lifecycle revision is required")

    await set_service_org(session, fence.org_id)
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
                {"session_id": str(fence.session_id), "org_id": str(fence.org_id)},
            )
        )
        .mappings()
        .one_or_none()
    )
    if not _matches_session_fence(row, fence):
        raise StaleLifecycleError(
            "source session lifecycle revision is stale or ineligible"
        )


def _matches_session_fence(row, fence: ExtractionSessionFence) -> bool:
    if row is None:
        return False
    if str(row["agent_id"]) != str(fence.agent_id):
        return False
    if row["status"] != "completed" or row["deleted_at"] is not None:
        return False
    return int(row["lifecycle_revision"]) == fence.expected_revision


async def enqueue_memory_lifecycle_event(
    session: AsyncSession, event: MemoryLifecycleEvent
) -> None:
    """Persist only lifecycle identifiers/metadata in the caller's transaction."""
    if event.revision < 1:
        raise ValueError("memory lifecycle revision must be positive")
    if event.event_type not in _EVENT_TYPES:
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
            "org_id": str(event.org_id),
            "memory_id": str(event.memory_id),
            "revision": event.revision,
            "event_type": event.event_type,
            "occurred_at": event.occurred_at or datetime.now(tz=UTC),
        },
    )


async def forget_memory_session(
    session: AsyncSession, request: ForgetMemory
) -> int:
    """Tombstone one scoped memory and fence extraction from its source session."""
    if request.expected_revision < 1:
        raise StaleLifecycleError("expected memory lifecycle revision must be positive")
    await lock_organization_for_memory_write(session, request.org_id)

    source_session_id = await _memory_source_session_id(session, request)
    if source_session_id is not None:
        source_session_id = await _lock_source_session(
            session, request, source_session_id
        )
    row = await _lock_forget_target(session, request)
    if row is None:
        raise MemoryNotFoundError()
    if bool(row["tombstoned"]) or int(row["lifecycle_revision"]) != request.expected_revision:
        raise StaleLifecycleError("memory lifecycle revision is stale")

    new_revision = await _tombstone_memory(session, request)
    if source_session_id is not None:
        await _advance_source_session_revision(session, request, source_session_id)
    await enqueue_memory_lifecycle_event(
        session,
        MemoryLifecycleEvent(
            org_id=request.org_id,
            memory_id=request.memory_id,
            revision=new_revision,
            event_type="forgotten",
        ),
    )
    return new_revision


async def _memory_source_session_id(
    session: AsyncSession, request: ForgetMemory
) -> UUID | None:
    result = await session.execute(
        text(
            """
            SELECT session_id
            FROM ibex_core.memories
            WHERE id = :memory_id AND org_id = :org_id AND agent_id = :agent_id
            """
        ),
        {
            "memory_id": str(request.memory_id),
            "org_id": str(request.org_id),
            "agent_id": str(request.agent_id),
        },
    )
    value = result.scalar_one_or_none()
    return UUID(str(value)) if value is not None else None


async def _lock_source_session(
    session: AsyncSession, request: ForgetMemory, session_id: UUID
) -> UUID | None:
    result = await session.execute(
        text(
            """
            SELECT id
            FROM ibex_core.sessions
            WHERE id = :session_id AND org_id = :org_id AND agent_id = :agent_id
            FOR UPDATE
            """
        ),
        {
            "session_id": str(session_id),
            "org_id": str(request.org_id),
            "agent_id": str(request.agent_id),
        },
    )
    value = result.scalar_one_or_none()
    return UUID(str(value)) if value is not None else None


async def _lock_forget_target(
    session: AsyncSession, request: ForgetMemory
):
    result = await session.execute(
        text(
            """
            SELECT lifecycle_revision, tombstoned
            FROM ibex_core.memories
            WHERE id = :memory_id AND org_id = :org_id AND agent_id = :agent_id
            FOR UPDATE
            """
        ),
        {
            "memory_id": str(request.memory_id),
            "org_id": str(request.org_id),
            "agent_id": str(request.agent_id),
        },
    )
    return result.mappings().one_or_none()


async def _tombstone_memory(session: AsyncSession, request: ForgetMemory) -> int:
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
            "memory_id": str(request.memory_id),
            "org_id": str(request.org_id),
            "agent_id": str(request.agent_id),
            "expected_revision": request.expected_revision,
        },
    )
    updated = result.mappings().one_or_none()
    if updated is None:
        raise StaleLifecycleError("memory lifecycle revision changed during forget")
    return int(updated["lifecycle_revision"])


async def _advance_source_session_revision(
    session: AsyncSession, request: ForgetMemory, session_id: UUID
) -> None:
    """Invalidate workers that captured the pre-forget source-session revision."""
    await session.execute(
        text(
            """
            UPDATE ibex_core.sessions
            SET lifecycle_revision = lifecycle_revision + 1
            WHERE id = :session_id AND org_id = :org_id AND agent_id = :agent_id
            """
        ),
        {
            "session_id": str(session_id),
            "org_id": str(request.org_id),
            "agent_id": str(request.agent_id),
        },
    )
