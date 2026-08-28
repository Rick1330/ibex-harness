"""Org-scoped content_hash lookup and retrieval_count bump (m3.C.2)."""

from __future__ import annotations

from dataclasses import dataclass
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.org_context import set_service_org


@dataclass(frozen=True, slots=True)
class ExactHashLookup:
    org_id: UUID
    agent_id: UUID
    content_hash: str


@dataclass(frozen=True, slots=True)
class RetrievalBump:
    org_id: UUID
    memory_id: UUID


async def find_active_by_content_hash(
    factory: async_sessionmaker[AsyncSession],
    lookup: ExactHashLookup,
) -> UUID | None:
    """Return active memory id for org/agent/hash, or None."""
    async with factory() as session, session.begin():
        await set_service_org(session, lookup.org_id)
        row = (
            await session.execute(
                text(  # nosemgrep: python.sqlalchemy.security.audit.avoid-sqlalchemy-text.avoid-sqlalchemy-text
                    """
                    SELECT id::text AS id
                    FROM ibex_core.memories
                    WHERE org_id = :org_id
                      AND agent_id = :agent_id
                      AND content_hash = :content_hash
                      AND status = 'active'
                      AND deleted_at IS NULL
                    LIMIT 1
                    """
                ),
                {
                    "org_id": str(lookup.org_id),
                    "agent_id": str(lookup.agent_id),
                    "content_hash": lookup.content_hash,
                },
            )
        ).one_or_none()
    if row is None:
        return None
    return UUID(str(row.id))


async def increment_retrieval_count(
    factory: async_sessionmaker[AsyncSession],
    bump: RetrievalBump,
) -> int:
    """Increment retrieval_count on exact-dedup hit; return new count."""
    async with factory() as session, session.begin():
        await set_service_org(session, bump.org_id)
        row = (
            await session.execute(
                text(  # nosemgrep: python.sqlalchemy.security.audit.avoid-sqlalchemy-text.avoid-sqlalchemy-text
                    """
                    UPDATE ibex_core.memories
                    SET retrieval_count = retrieval_count + 1,
                        last_retrieved_at = NOW(),
                        updated_at = NOW()
                    WHERE id = :memory_id
                      AND org_id = :org_id
                      AND status = 'active'
                      AND deleted_at IS NULL
                    RETURNING retrieval_count
                    """
                ),
                {
                    "memory_id": str(bump.memory_id),
                    "org_id": str(bump.org_id),
                },
            )
        ).one_or_none()
        if row is None:
            msg = "retrieval_count bump expected 1 row"
            raise RuntimeError(msg)
        return int(row.retrieval_count)
