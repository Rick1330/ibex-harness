"""Org-scoped feedback ledger upsert + usefulness recompute (single transaction)."""

from __future__ import annotations

from typing import Any
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.exceptions import MemoryNotFoundError, ValidationError
from app.feedback.models import ApplyFeedbackCommand, ApplyFeedbackResult, FeedbackKind
from app.feedback.score import laplace_usefulness
from app.org_context import set_service_org
from app.write.models import MemoryRow
from app.write.persist import memory_row_from_mapping


async def apply_feedback_session(
    factory: async_sessionmaker[AsyncSession],
    command: ApplyFeedbackCommand,
) -> tuple[ApplyFeedbackResult, MemoryRow]:
    """Upsert ledger vote and update memories.usefulness_score atomically."""
    async with factory() as session, session.begin():
        await set_service_org(session, command.org_id)
        memory = await _load_memory(session, command)
        await _upsert_ledger(session, command)
        positive, negative = await _count_votes(session, command)
        score = laplace_usefulness(positive, negative)
        updated = await _update_usefulness(session, command, score)
        result = ApplyFeedbackResult(
            memory_id=command.memory_id,
            feedback=command.feedback,
            new_usefulness_score=score,
            total_positive_feedback=positive,
            total_negative_feedback=negative,
            memory_agent_id=memory.agent_id,
        )
        return result, updated


async def _load_memory(
    session: AsyncSession,
    command: ApplyFeedbackCommand,
) -> MemoryRow:
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
                WHERE id = :memory_id
                  AND org_id = :org_id
                  AND deleted_at IS NULL
                """
            ),
            {"memory_id": str(command.memory_id), "org_id": str(command.org_id)},
        )
    ).one_or_none()
    if row is None:
        raise MemoryNotFoundError()
    return memory_row_from_mapping(row)


async def _upsert_ledger(session: AsyncSession, command: ApplyFeedbackCommand) -> None:
    params: dict[str, Any] = {
        "org_id": str(command.org_id),
        "memory_id": str(command.memory_id),
        "agent_id": str(command.agent_id),
        "feedback": command.feedback.value,
        "session_id": str(command.session_id) if command.session_id else None,
        "trace_id": str(command.trace_id) if command.trace_id else None,
        "notes": command.notes,
    }
    await session.execute(
        text(  # nosemgrep: python.sqlalchemy.security.audit.avoid-sqlalchemy-text.avoid-sqlalchemy-text
            """
            INSERT INTO ibex_core.memory_feedback (
                org_id, memory_id, agent_id, feedback,
                session_id, trace_id, notes
            ) VALUES (
                :org_id, :memory_id, :agent_id, :feedback,
                :session_id, :trace_id, :notes
            )
            ON CONFLICT (org_id, memory_id, agent_id)
            DO UPDATE SET
                feedback = EXCLUDED.feedback,
                session_id = EXCLUDED.session_id,
                trace_id = EXCLUDED.trace_id,
                notes = EXCLUDED.notes,
                updated_at = NOW()
            """
        ),
        params,
    )


async def _count_votes(
    session: AsyncSession,
    command: ApplyFeedbackCommand,
) -> tuple[int, int]:
    row = (
        await session.execute(
            text(  # nosemgrep: python.sqlalchemy.security.audit.avoid-sqlalchemy-text.avoid-sqlalchemy-text
                """
                SELECT
                    COUNT(*) FILTER (WHERE feedback = 'positive')::int AS positive,
                    COUNT(*) FILTER (WHERE feedback = 'negative')::int AS negative
                FROM ibex_core.memory_feedback
                WHERE org_id = :org_id
                  AND memory_id = :memory_id
                """
            ),
            {"org_id": str(command.org_id), "memory_id": str(command.memory_id)},
        )
    ).one()
    return int(row.positive), int(row.negative)


async def _update_usefulness(
    session: AsyncSession,
    command: ApplyFeedbackCommand,
    score: float,
) -> MemoryRow:
    row = (
        await session.execute(
            text(  # nosemgrep: python.sqlalchemy.security.audit.avoid-sqlalchemy-text.avoid-sqlalchemy-text
                """
                UPDATE ibex_core.memories
                SET usefulness_score = :score,
                    updated_at = NOW()
                WHERE id = :memory_id
                  AND org_id = :org_id
                  AND deleted_at IS NULL
                RETURNING
                    id, org_id, agent_id, content, content_tokens, category, status,
                    confidence, source, pii_detected, pii_redacted, session_id,
                    metadata, retrieval_count, usefulness_score,
                    valid_from, valid_until, created_at, updated_at
                """
            ),
            {
                "score": score,
                "memory_id": str(command.memory_id),
                "org_id": str(command.org_id),
            },
        )
    ).one_or_none()
    if row is None:
        raise MemoryNotFoundError()
    return memory_row_from_mapping(row)


def require_agent_id(agent_id: UUID | None) -> UUID:
    if agent_id is None:
        raise ValidationError(
            "agent-scoped token required for feedback",
            field="agent_id",
            field_code="MISSING_AGENT_ID",
        )
    return agent_id


def parse_feedback_kind(raw: str) -> FeedbackKind:
    try:
        return FeedbackKind(raw)
    except ValueError as exc:
        raise ValidationError(
            "feedback must be positive, negative, or neutral",
            field="feedback",
            field_code="INVALID_ENUM",
        ) from exc
