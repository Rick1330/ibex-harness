"""Org-scoped candidate load + supersession persist (m3.C.3)."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.conflict.intervals import ValidityInterval
from app.conflict.types import CandidateMemory, SupersedeApply
from app.org_context import set_service_org


@dataclass(frozen=True, slots=True)
class CandidateLoad:
    org_id: UUID
    memory_ids: tuple[UUID, ...]


@dataclass(frozen=True, slots=True)
class RelationshipInsert:
    org_id: UUID
    source_memory_id: UUID
    target_memory_id: UUID
    relationship_type: str
    confidence: float = 0.90
    resolution_notes: str | None = None


async def load_candidate_memories(
    factory: async_sessionmaker[AsyncSession],
    load: CandidateLoad,
) -> list[CandidateMemory]:
    """Load active candidate rows for conflict evaluation (org-scoped)."""
    if not load.memory_ids:
        return []
    async with factory() as session, session.begin():
        await set_service_org(session, load.org_id)
        rows = (
            await session.execute(
                text(  # nosemgrep: python.sqlalchemy.security.audit.avoid-sqlalchemy-text.avoid-sqlalchemy-text
                    """
                    SELECT id::text AS id,
                           content,
                           valid_from,
                           valid_until,
                           confidence::float8 AS confidence
                    FROM ibex_core.memories
                    WHERE org_id = :org_id
                      AND id = ANY(CAST(:ids AS uuid[]))
                      AND status = 'active'
                      AND deleted_at IS NULL
                    """
                ),
                {
                    "org_id": str(load.org_id),
                    "ids": [str(i) for i in load.memory_ids],
                },
            )
        ).all()
    by_id = {UUID(str(r.id)): r for r in rows}
    out: list[CandidateMemory] = []
    for mid in load.memory_ids:
        row = by_id.get(mid)
        if row is None:
            continue
        out.append(
            CandidateMemory(
                memory_id=mid,
                content=str(row.content),
                interval=ValidityInterval(
                    valid_from=_aware(row.valid_from),
                    valid_until=_aware_opt(row.valid_until),
                ),
                confidence=float(row.confidence),
            )
        )
    return out


async def apply_supersession_session(
    session: AsyncSession,
    apply: SupersedeApply,
) -> None:
    """Mark target superseded, close interval, insert supersedes edge (caller txn)."""
    closed_at = apply.closed_at or datetime.now(tz=UTC)
    await set_service_org(session, apply.org_id)
    result = await session.execute(
        text(  # nosemgrep: python.sqlalchemy.security.audit.avoid-sqlalchemy-text.avoid-sqlalchemy-text
            """
            UPDATE ibex_core.memories
            SET status = 'superseded',
                superseded_by = :new_id,
                valid_until = LEAST(COALESCE(valid_until, :closed_at), :closed_at),
                updated_at = NOW()
            WHERE id = :target_id
              AND org_id = :org_id
              AND status = 'active'
              AND deleted_at IS NULL
            """
        ),
        {
            "new_id": str(apply.new_memory_id),
            "closed_at": closed_at,
            "target_id": str(apply.target_memory_id),
            "org_id": str(apply.org_id),
        },
    )
    if result.rowcount != 1:
        msg = f"supersede update expected 1 row, got {result.rowcount}"
        raise RuntimeError(msg)
    await session.execute(
        text(  # nosemgrep: python.sqlalchemy.security.audit.avoid-sqlalchemy-text.avoid-sqlalchemy-text
            """
            INSERT INTO ibex_core.memory_relationships (
                org_id, source_memory_id, target_memory_id,
                relationship_type, confidence, resolution_notes
            ) VALUES (
                :org_id, :source_id, :target_id,
                'supersedes', :confidence, :notes
            )
            ON CONFLICT (source_memory_id, target_memory_id, relationship_type)
            DO NOTHING
            """
        ),
        {
            "org_id": str(apply.org_id),
            "source_id": str(apply.new_memory_id),
            "target_id": str(apply.target_memory_id),
            "confidence": apply.confidence,
            "notes": "m3.c.3 auto-supersede",
        },
    )


async def apply_supersession(
    factory: async_sessionmaker[AsyncSession],
    apply: SupersedeApply,
) -> None:
    """Mark target superseded, close interval, insert supersedes edge."""
    async with factory() as session, session.begin():
        await apply_supersession_session(session, apply)


async def insert_relationship(
    factory: async_sessionmaker[AsyncSession],
    insert: RelationshipInsert,
) -> None:
    """Insert a typed memory_relationships edge (org-scoped)."""
    async with factory() as session, session.begin():
        await set_service_org(session, insert.org_id)
        await session.execute(
            text(  # nosemgrep: python.sqlalchemy.security.audit.avoid-sqlalchemy-text.avoid-sqlalchemy-text
                """
                INSERT INTO ibex_core.memory_relationships (
                    org_id, source_memory_id, target_memory_id,
                    relationship_type, confidence, resolution_notes
                ) VALUES (
                    :org_id, :source_id, :target_id,
                    :rel_type, :confidence, :notes
                )
                ON CONFLICT (source_memory_id, target_memory_id, relationship_type)
                DO NOTHING
                """
            ),
            {
                "org_id": str(insert.org_id),
                "source_id": str(insert.source_memory_id),
                "target_id": str(insert.target_memory_id),
                "rel_type": insert.relationship_type,
                "confidence": insert.confidence,
                "notes": insert.resolution_notes,
            },
        )


def _aware(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value


def _aware_opt(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    return _aware(value)
