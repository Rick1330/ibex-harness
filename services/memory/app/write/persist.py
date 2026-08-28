"""Session-scoped memory insert, supersession, and escalation persistence."""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.conflict.types import ConflictDecision, ConflictOutcome
from app.dedup.hash import content_hash_sha256
from app.org_context import set_service_org
from app.pipeline.context import WriteContext
from app.write.labels import LabelInsert
from app.write.models import CreateMemoryCommand, MemoryRow


@dataclass(frozen=True, slots=True)
class EscalationInsert:
    org_id: UUID
    new_memory_id: UUID
    candidate_memory_id: UUID
    conflict_type: str
    subject_key: str | None
    reason: str | None


def content_token_count(content: str) -> int:
    return max(1, len(content.split()))


def _persist_metadata(command: CreateMemoryCommand) -> dict[str, Any]:
    meta = dict(command.metadata or {})
    meta["visibility"] = command.visibility
    meta["pinned"] = command.pinned
    if command.tags:
        meta["tags"] = list(command.tags)
    return meta


def _split_presentation_metadata(
    meta: dict[str, Any],
) -> tuple[str, bool, tuple[str, ...], dict[str, Any]]:
    stored = dict(meta)
    visibility = str(stored.pop("visibility", "agent"))
    pinned = bool(stored.pop("pinned", False))
    tags_raw = stored.pop("tags", [])
    tags = tuple(str(tag) for tag in tags_raw) if isinstance(tags_raw, list) else ()
    return visibility, pinned, tags, stored


def _row_from_mapping(row: Any) -> MemoryRow:
    meta = row.metadata
    if isinstance(meta, str):
        meta = json.loads(meta)
    if not isinstance(meta, dict):
        meta = {}
    visibility, pinned, tags, metadata = _split_presentation_metadata(meta)
    return MemoryRow(
        id=UUID(str(row.id)),
        org_id=UUID(str(row.org_id)),
        agent_id=UUID(str(row.agent_id)),
        content=str(row.content),
        content_tokens=int(row.content_tokens),
        category=str(row.category),
        confidence=float(row.confidence),
        status=str(row.status),
        source=str(row.source),
        pii_detected=bool(row.pii_detected),
        pii_redacted=bool(row.pii_redacted),
        session_id=UUID(str(row.session_id)) if row.session_id else None,
        visibility=visibility,
        pinned=pinned,
        tags=tags,
        metadata=metadata,
        retrieval_count=int(row.retrieval_count),
        usefulness_score=float(row.usefulness_score),
        valid_from=_aware(row.valid_from),
        valid_until=_aware_opt(row.valid_until),
        created_at=_aware(row.created_at),
        updated_at=_aware(row.updated_at),
    )


async def insert_memory_session(
    session: AsyncSession,
    *,
    command: CreateMemoryCommand,
    ctx: WriteContext,
) -> MemoryRow:
    """Insert a memories row; caller owns the transaction."""
    await set_service_org(session, command.org_id)
    valid_from = command.valid_from or ctx.valid_from or datetime.now(tz=UTC)
    content_hash = ctx.content_hash or content_hash_sha256(ctx.content)
    params: dict[str, Any] = {
        "org_id": str(command.org_id),
        "agent_id": str(command.agent_id),
        "session_id": str(command.session_id) if command.session_id else None,
        "content": ctx.content,
        "content_hash": content_hash,
        "content_tokens": content_token_count(ctx.content),
        "category": command.labels[0].label,
        "status": ctx.status,
        "confidence": command.confidence,
        "source": "user_provided",
        "pii_detected": ctx.pii_detected,
        "pii_redacted": ctx.pii_redacted,
        "metadata": json.dumps(_persist_metadata(command)),
        "valid_from": valid_from,
        "valid_until": command.valid_until or ctx.valid_until,
    }
    row = (
        await session.execute(
            text(  # nosemgrep: python.sqlalchemy.security.audit.avoid-sqlalchemy-text.avoid-sqlalchemy-text
                """
                INSERT INTO ibex_core.memories (
                    org_id, agent_id, session_id, content, content_hash, content_tokens,
                    category, status, confidence, source, pii_detected, pii_redacted,
                    metadata, valid_from, valid_until
                ) VALUES (
                    :org_id, :agent_id, :session_id, :content, :content_hash, :content_tokens,
                    :category, :status, :confidence, :source, :pii_detected, :pii_redacted,
                    CAST(:metadata AS jsonb), :valid_from, :valid_until
                )
                RETURNING
                    id, org_id, agent_id, content, content_tokens, category, status,
                    confidence, source, pii_detected, pii_redacted, session_id,
                    metadata, retrieval_count, usefulness_score,
                    valid_from, valid_until, created_at, updated_at
                """
            ),
            params,
        )
    ).one()
    return _row_from_mapping(row)


async def insert_labels_session(
    session: AsyncSession,
    inserts: list[LabelInsert],
) -> int:
    if not inserts:
        return 0
    await set_service_org(session, inserts[0].org_id)
    for item in inserts:
        await session.execute(
            text(  # nosemgrep: python.sqlalchemy.security.audit.avoid-sqlalchemy-text.avoid-sqlalchemy-text
                """
                INSERT INTO ibex_core.memory_labels (
                    memory_id, org_id, label, confidence
                ) VALUES (
                    :memory_id, :org_id, :label, :confidence
                )
                """
            ),
            {
                "memory_id": str(item.memory_id),
                "org_id": str(item.org_id),
                "label": item.label,
                "confidence": item.confidence,
            },
        )
    return len(inserts)


async def reload_memory_session(
    session: AsyncSession,
    *,
    org_id: UUID,
    memory_id: UUID,
) -> MemoryRow:
    await set_service_org(session, org_id)
    row = (
        await session.execute(
            text(  # nosemgrep: python.sqlalchemy.security.audit.avoid-sqlalchemy-text.avoid-sqlalchemy-text
                """
                SELECT
                    id, org_id, agent_id, content, content_tokens, category, status,
                    confidence, source, pii_detected, pii_redacted, session_id,
                    metadata, retrieval_count, usefulness_score,
                    valid_from, valid_until, created_at, updated_at
                FROM ibex_core.memories
                WHERE id = :memory_id AND org_id = :org_id
                """
            ),
            {"memory_id": str(memory_id), "org_id": str(org_id)},
        )
    ).one()
    return _row_from_mapping(row)


async def insert_escalations_session(
    session: AsyncSession,
    inserts: list[EscalationInsert],
) -> int:
    if not inserts:
        return 0
    await set_service_org(session, inserts[0].org_id)
    for item in inserts:
        await session.execute(
            text(  # nosemgrep: python.sqlalchemy.security.audit.avoid-sqlalchemy-text.avoid-sqlalchemy-text
                """
                INSERT INTO ibex_core.memory_conflict_escalations (
                    org_id, new_memory_id, candidate_memory_id,
                    conflict_type, status, subject_key, reason
                ) VALUES (
                    :org_id, :new_id, :candidate_id,
                    :conflict_type, 'pending', :subject_key, :reason
                )
                """
            ),
            {
                "org_id": str(item.org_id),
                "new_id": str(item.new_memory_id),
                "candidate_id": str(item.candidate_memory_id),
                "conflict_type": item.conflict_type,
                "subject_key": item.subject_key,
                "reason": item.reason,
            },
        )
    return len(inserts)


def escalations_from_decisions(
    org_id: UUID,
    new_memory_id: UUID,
    decisions: list[ConflictDecision],
) -> list[EscalationInsert]:
    out: list[EscalationInsert] = []
    for decision in decisions:
        if decision.outcome != ConflictOutcome.ESCALATE_PENDING:
            continue
        out.append(
            EscalationInsert(
                org_id=org_id,
                new_memory_id=new_memory_id,
                candidate_memory_id=decision.candidate_id,
                conflict_type=decision.outcome.value,
                subject_key=decision.subject_key,
                reason=decision.notes or None,
            )
        )
    return out


def _aware(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value


def _aware_opt(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    return _aware(value)
