"""Memory write orchestrator — pipeline stages 1–6 + transactional persist."""

from __future__ import annotations

import logging
from collections.abc import Awaitable, Callable
from uuid import UUID

from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.conflict.persist import apply_supersession_session
from app.conflict.types import SupersedeApply
from app.dedup.persist import (
    ExactHashLookup,
    RetrievalBump,
    find_active_by_content_hash,
    increment_retrieval_count,
)
from app.exceptions import DuplicateMemoryError, EmbeddingServiceError, ValidationError
from app.pipeline.context import WriteContext
from app.pipeline.write import WritePipeline
from app.write.embed_context import reset_write_org_id, set_write_org_id
from app.write.errors import is_active_content_hash_violation
from app.write.metrics import ESCALATIONS_INSERTED
from app.write.models import CreateMemoryCommand, WriteOutcome, WriteOutcomeKind
from app.write.persist import (
    escalations_from_decisions,
    insert_escalations_session,
    insert_memory_session,
)

logger = logging.getLogger(__name__)

_VALIDATION_ERRORS: dict[str, tuple[str, str | None]] = {
    "content_empty": ("Content must not be empty", "content"),
    "content_too_long": ("Content exceeds maximum length", "content"),
    "agent_id_required": ("agent_id is required", "agent_id"),
    "embedding_required": ("Embedding is required", None),
}


class MemoryWriteOrchestrator:
    """Runs WritePipeline then persists (steps 7–9 DB portion)."""

    def __init__(
        self,
        pipeline: WritePipeline,
        session_factory: async_sessionmaker[AsyncSession],
        *,
        after_commit: Callable[[WriteOutcome], Awaitable[None]] | None = None,
    ) -> None:
        self._pipeline = pipeline
        self._factory = session_factory
        self._after_commit = after_commit

    async def create(self, command: CreateMemoryCommand) -> WriteOutcome:
        ctx = await self._run_pipeline(command)
        self._raise_for_pipeline_ctx(ctx)

        if ctx.is_exact_duplicate:
            if ctx.existing_memory_id is None:
                msg = "exact duplicate without existing_memory_id"
                raise RuntimeError(msg)
            raise DuplicateMemoryError(ctx.existing_memory_id)

        if ctx.status == "quarantined":
            outcome = await self._persist_quarantine(command, ctx)
            await self._run_after_commit(outcome)
            return outcome

        outcome = await self._persist_active(command, ctx)
        await self._run_after_commit(outcome)
        return outcome

    async def _run_pipeline(self, command: CreateMemoryCommand) -> WriteContext:
        ctx = WriteContext(
            org_id=command.org_id,
            agent_id=command.agent_id,
            content=command.content,
            valid_from=command.valid_from,
            valid_until=command.valid_until,
        )
        token = set_write_org_id(command.org_id)
        try:
            return await self._pipeline.run(ctx)
        except Exception as exc:
            if _is_embedding_failure(exc):
                raise EmbeddingServiceError("Embedding service unavailable") from exc
            raise
        finally:
            reset_write_org_id(token)

    def _raise_for_pipeline_ctx(self, ctx: WriteContext) -> None:
        if ctx.error is None:
            return
        message, field = _VALIDATION_ERRORS.get(ctx.error, ("Invalid request", None))
        raise ValidationError(message, field=field, field_code=ctx.error)

    async def _run_after_commit(self, outcome: WriteOutcome) -> None:
        if self._after_commit is None:
            return
        try:
            await self._after_commit(outcome)
        except Exception:
            logger.warning(
                "after_commit failed org_id=%s memory_id=%s",
                outcome.memory.org_id,
                outcome.memory.id,
                exc_info=True,
            )

    async def _persist_quarantine(
        self, command: CreateMemoryCommand, ctx: WriteContext
    ) -> WriteOutcome:
        async with self._factory() as session, session.begin():
            memory = await insert_memory_session(session, command=command, ctx=ctx)
        return WriteOutcome(
            kind=WriteOutcomeKind.QUARANTINED,
            memory=memory,
        )

    async def _persist_active(
        self, command: CreateMemoryCommand, ctx: WriteContext
    ) -> WriteOutcome:
        memory = await self._insert_active_memory(command, ctx)
        return self._created_outcome(memory, ctx)

    async def _insert_active_memory(
        self, command: CreateMemoryCommand, ctx: WriteContext
    ):
        if ctx.content_hash is None:
            msg = "content_hash required for active persist"
            raise RuntimeError(msg)
        try:
            return await self._insert_active_memory_tx(command, ctx)
        except IntegrityError as exc:
            await self._raise_duplicate_on_hash_violation(command, ctx, exc)

    async def _insert_active_memory_tx(
        self, command: CreateMemoryCommand, ctx: WriteContext
    ):
        escalation_count = 0
        async with self._factory() as session, session.begin():
            memory = await insert_memory_session(session, command=command, ctx=ctx)
            escalation_count = await self._apply_supersession_and_escalations(
                session, command, memory.id, ctx
            )
        if escalation_count:
            ESCALATIONS_INSERTED.inc(escalation_count)
        return memory

    async def _raise_duplicate_on_hash_violation(
        self,
        command: CreateMemoryCommand,
        ctx: WriteContext,
        exc: IntegrityError,
    ) -> None:
        if not is_active_content_hash_violation(exc):
            raise exc
        existing_id = await self._handle_hash_race(command, ctx.content_hash)
        raise DuplicateMemoryError(existing_id) from exc

    async def _apply_supersession_and_escalations(
        self,
        session,
        command: CreateMemoryCommand,
        memory_id: UUID,
        ctx: WriteContext,
    ) -> int:
        for target_id in ctx.pending_supersede_targets:
            await apply_supersession_session(
                session,
                SupersedeApply(
                    org_id=command.org_id,
                    new_memory_id=memory_id,
                    target_memory_id=target_id,
                ),
            )
        escalations = escalations_from_decisions(
            command.org_id, memory_id, ctx.conflict_decisions
        )
        return await insert_escalations_session(session, escalations)

    def _created_outcome(self, memory, ctx: WriteContext) -> WriteOutcome:
        embedding_model: str | None = None
        embedding_tuple: tuple[float, ...] | None = None
        if ctx.embedding is not None:
            embedding_tuple = tuple(ctx.embedding)
            embedding_model = "bge-m3"
        return WriteOutcome(
            kind=WriteOutcomeKind.CREATED,
            memory=memory,
            near_duplicate_candidates=tuple(ctx.near_duplicate_candidates),
            conflict_decisions=tuple(ctx.conflict_decisions),
            embedding=embedding_tuple,
            embedding_model=embedding_model,
        )

    async def _handle_hash_race(
        self, command: CreateMemoryCommand, content_hash: str
    ) -> UUID:
        existing = await find_active_by_content_hash(
            self._factory,
            ExactHashLookup(
                org_id=command.org_id,
                agent_id=command.agent_id,
                content_hash=content_hash,
            ),
        )
        if existing is None:
            msg = "unique violation without existing active memory"
            raise RuntimeError(msg)
        await increment_retrieval_count(
            self._factory,
            RetrievalBump(org_id=command.org_id, memory_id=existing),
        )
        logger.info(
            "content_hash race resolved org_id=%s agent_id=%s winner=%s",
            command.org_id,
            command.agent_id,
            existing,
        )
        return existing


def _is_embedding_failure(exc: BaseException) -> bool:
    name = type(exc).__name__
    return name in {
        "EmbeddingClientError",
        "EmbeddingTimeoutError",
        "EmbeddingUnavailableError",
        "EmbeddingRejectedError",
    }
