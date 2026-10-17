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

_ADVISORY_LOCK_SQL = "SELECT pg_advisory_xact_lock_shared(hashtext(CAST(:org_id AS text)))"

_ORG_STATUS_SQL = """
    SELECT status, deleted_at
    FROM ibex_core.organizations
    WHERE id = :org_id
    FOR SHARE
"""

_SESSION_FENCE_SQL = """
    SELECT agent_id, status, deleted_at, lifecycle_revision
    FROM ibex_core.sessions
    WHERE id = :session_id AND org_id = :org_id
    FOR UPDATE
"""

_INSERT_EVENT_SQL = """
    INSERT INTO ibex_core.memory_lifecycle_outbox (
        org_id, memory_id, revision, schema_version, event_type, occurred_at
    ) VALUES (
        :org_id, :memory_id, :revision, 1, :event_type, :occurred_at
    )
"""

_MEMORY_SOURCE_SESSION_SQL = """
    SELECT session_id
    FROM ibex_core.memories
    WHERE id = :memory_id AND org_id = :org_id AND agent_id = :agent_id
"""

_LOCK_SOURCE_SESSION_SQL = """
    SELECT id
    FROM ibex_core.sessions
    WHERE id = :session_id AND org_id = :org_id AND agent_id = :agent_id
    FOR UPDATE
"""

_LOCK_FORGET_TARGET_SQL = """
    SELECT lifecycle_revision, tombstoned
    FROM ibex_core.memories
    WHERE id = :memory_id AND org_id = :org_id AND agent_id = :agent_id
    FOR UPDATE
"""

_TOMBSTONE_SQL = """
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

_ADVANCE_SESSION_SQL = """
    UPDATE ibex_core.sessions
    SET lifecycle_revision = lifecycle_revision + 1
    WHERE id = :session_id AND org_id = :org_id AND agent_id = :agent_id
"""


def _memory_scope_params(request: ForgetMemory) -> dict[str, object]:
    return {
        "memory_id": str(request.memory_id),
        "org_id": str(request.org_id),
        "agent_id": str(request.agent_id),
    }


def _session_scope_params(request: ForgetMemory, session_id: UUID) -> dict[str, object]:
    return {
        "session_id": str(session_id),
        "org_id": str(request.org_id),
        "agent_id": str(request.agent_id),
    }


async def _execute(
    session: AsyncSession, statement: str, params: dict[str, object]
) -> None:
    await session.execute(text(statement), params)


async def _fetch_mapping(
    session: AsyncSession, statement: str, params: dict[str, object]
):
    result = await session.execute(text(statement), params)
    return result.mappings().one_or_none()


async def _fetch_uuid(
    session: AsyncSession, statement: str, params: dict[str, object]
) -> UUID | None:
    value = (await session.execute(text(statement), params)).scalar_one_or_none()
    return UUID(str(value)) if value is not None else None


async def lock_organization_for_memory_write(session: AsyncSession, org_id: UUID) -> None:
    """Serialize memory mutations against org purge and reject cancelled orgs."""
    await set_service_org(session, org_id)
    await _execute(session, _ADVISORY_LOCK_SQL, {"org_id": str(org_id)})
    row = await _fetch_mapping(session, _ORG_STATUS_SQL, {"org_id": str(org_id)})
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
    row = await _fetch_mapping(
        session,
        _SESSION_FENCE_SQL,
        {"session_id": str(fence.session_id), "org_id": str(fence.org_id)},
    )
    if not _matches_session_fence(row, fence):
        raise StaleLifecycleError("source session lifecycle revision is stale or ineligible")


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
    await _execute(
        session,
        _INSERT_EVENT_SQL,
        {
            "org_id": str(event.org_id),
            "memory_id": str(event.memory_id),
            "revision": event.revision,
            "event_type": event.event_type,
            "occurred_at": event.occurred_at or datetime.now(tz=UTC),
        },
    )


async def forget_memory_session(session: AsyncSession, request: ForgetMemory) -> int:
    """Tombstone one scoped memory and fence extraction from its source session."""
    if request.expected_revision < 1:
        raise StaleLifecycleError("expected memory lifecycle revision must be positive")
    await lock_organization_for_memory_write(session, request.org_id)

    source_session_id = await _resolve_source_session(session, request)
    await _require_forget_target(session, request)
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


async def _resolve_source_session(
    session: AsyncSession, request: ForgetMemory
) -> UUID | None:
    source_session_id = await _memory_source_session_id(session, request)
    if source_session_id is None:
        return None
    return await _lock_source_session(session, request, source_session_id)


async def _require_forget_target(session: AsyncSession, request: ForgetMemory) -> None:
    row = await _lock_forget_target(session, request)
    if row is None:
        raise MemoryNotFoundError()
    if bool(row["tombstoned"]) or int(row["lifecycle_revision"]) != request.expected_revision:
        raise StaleLifecycleError("memory lifecycle revision is stale")


async def _memory_source_session_id(
    session: AsyncSession, request: ForgetMemory
) -> UUID | None:
    return await _fetch_uuid(session, _MEMORY_SOURCE_SESSION_SQL, _memory_scope_params(request))


async def _lock_source_session(
    session: AsyncSession, request: ForgetMemory, session_id: UUID
) -> UUID | None:
    return await _fetch_uuid(
        session, _LOCK_SOURCE_SESSION_SQL, _session_scope_params(request, session_id)
    )


async def _lock_forget_target(session: AsyncSession, request: ForgetMemory):
    return await _fetch_mapping(session, _LOCK_FORGET_TARGET_SQL, _memory_scope_params(request))


async def _tombstone_memory(session: AsyncSession, request: ForgetMemory) -> int:
    params = _memory_scope_params(request)
    params["expected_revision"] = request.expected_revision
    updated = await _fetch_mapping(session, _TOMBSTONE_SQL, params)
    if updated is None:
        raise StaleLifecycleError("memory lifecycle revision changed during forget")
    return int(updated["lifecycle_revision"])


async def _advance_source_session_revision(
    session: AsyncSession, request: ForgetMemory, session_id: UUID
) -> None:
    """Invalidate workers that captured the pre-forget source-session revision."""
    await _execute(
        session, _ADVANCE_SESSION_SQL, _session_scope_params(request, session_id)
    )
