"""HTTP support for POST /v1/memories: write orchestration + response assembly.

The route sequences authorization, idempotency and the write orchestrator; this
module holds the parts that turn a request into a ``CreateMemoryCommand`` and a
``WriteOutcome`` into the 201/202 response (including its idempotency
finalization). Error classification lives in ``memory_write_errors`` and the
ledger claim lifecycle in ``memory_write_idempotency``.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any
from uuid import UUID

from fastapi import Response

from app.exceptions import (
    DuplicateMemoryError,
    EmbeddingServiceError,
    MemoryOrganizationUnavailableError,
    StaleLifecycleError,
    ValidationError,
)
from app.routers.memory_write_errors import (
    http_error_for_unknown_agent,
    http_error_for_write,
    http_internal_error_for_write,
    is_unknown_agent_violation,
)
from app.routers.memory_write_idempotency import (
    IdempotencyHandle,
    commit_idempotency_fail_closed,
    erased_create_prepare,
    release_idempotency,
)
from app.schemas.memories import (
    CreateMemoryMeta,
    CreateMemoryRequest,
    CreateMemoryResponse,
    DeduplicationMeta,
    MemoryData,
    QuarantineMemoryData,
    QuarantineMemoryResponse,
)
from app.write.labels import MemoryLabelInput, resolve_write_labels
from app.write.models import CreateMemoryCommand, MemoryRow, WriteOutcome

logger = logging.getLogger(__name__)

#: Stable quarantine messages. ``meta.message`` is caller-visible contract: a
#: reason keeps its exact wording once shipped.
QUARANTINE_MESSAGES: dict[str, str] = {
    "pii_low_confidence": "Memory quarantined for review due to PII detection",
    "prompt_injection_heuristic": (
        "Memory quarantined for review due to suspected prompt injection"
    ),
}


@dataclass(frozen=True, slots=True)
class CreatedResponseContext:
    outcome: WriteOutcome
    org_id: UUID
    elapsed_ms: int
    idem: IdempotencyHandle
    response: Response


async def create_memory_outcome(
    orchestrator: Any,
    command: CreateMemoryCommand,
    idem: IdempotencyHandle,
    org_id: UUID,
) -> WriteOutcome:
    """Run the write and map every failure to its stable HTTP envelope.

    The domain errors keep their specific status; an unknown agent is the
    composite-FK 404; anything else is a logged 500. The idempotency slot is
    released on every failure path so a retry can re-claim it.
    """
    try:
        return await orchestrator.create(command)
    except (
        DuplicateMemoryError,
        ValidationError,
        EmbeddingServiceError,
        StaleLifecycleError,
        MemoryOrganizationUnavailableError,
    ) as exc:
        await release_idempotency(idem)
        raise http_error_for_write(exc) from exc
    except Exception as exc:
        await release_idempotency(idem)
        if is_unknown_agent_violation(exc):
            raise http_error_for_unknown_agent() from exc
        logger.exception(
            "memory write failed org_id=%s agent_id=%s error_class=%s",
            org_id,
            command.agent_id,
            type(exc).__name__,
        )
        raise http_internal_error_for_write() from exc


def memory_command_from_request(
    request: CreateMemoryRequest,
    org_id: UUID,
) -> CreateMemoryCommand:
    label_inputs: tuple[MemoryLabelInput, ...] | None = None
    if request.labels is not None:
        label_inputs = tuple(
            MemoryLabelInput(label=item.label, confidence=item.confidence)
            for item in request.labels
        )
    resolved = resolve_write_labels(
        category=request.category,
        confidence=request.confidence,
        labels=label_inputs,
    )
    return CreateMemoryCommand(
        org_id=org_id,
        agent_id=request.agent_id,
        content=request.content,
        category=resolved[0].label,
        confidence=request.confidence,
        session_id=request.session_id,
        visibility=request.visibility,
        tags=tuple(request.tags),
        pinned=request.pinned,
        metadata=request.metadata,
        valid_from=request.valid_from,
        valid_until=request.valid_until,
        expires_at=request.expires_at,
        expected_session_revision=request.expected_session_revision,
        labels=resolved,
    )


def memory_data_from_outcome(outcome: WriteOutcome, org_id: UUID) -> MemoryData:
    memory = outcome.memory
    return MemoryData(
        id=memory.id,
        agent_id=memory.agent_id,
        org_id=org_id,
        content=memory.content,
        content_tokens=memory.content_tokens,
        category=memory.category,
        confidence=memory.confidence,
        source=memory.source,
        status=memory.status,
        visibility=memory.visibility,
        pinned=memory.pinned,
        tags=list(memory.tags),
        retrieval_count=memory.retrieval_count,
        usefulness_score=memory.usefulness_score,
        pii_detected=memory.pii_detected,
        session_id=memory.session_id,
        metadata=memory.metadata,
        created_at=memory.created_at,
        updated_at=memory.updated_at,
        lifecycle_revision=memory.lifecycle_revision,
    )


def quarantine_reason_for(memory: MemoryRow) -> str:
    """Map a persisted quarantine row back to the reason that caused it.

    The pipeline keeps ``quarantine_reason`` in memory only — there is no column
    for it — so the response derives the reason from ``pii_detected``, which is
    persisted. ``InjectionStage`` runs before ``PiiStage`` and stops the pipeline
    on a match, so ``pii_detected`` is set only when PII caused the quarantine.
    A row that is neither is reported as the injection heuristic: unknown
    quarantine content is untrusted content.
    """
    if memory.pii_detected:
        return "pii_low_confidence"
    return "prompt_injection_heuristic"


async def finalize_quarantine_response(
    *,
    outcome: WriteOutcome,
    idem: IdempotencyHandle,
    response: Response,
) -> QuarantineMemoryResponse:
    """Record the 202 and store it as the replayed response for the key."""
    response.status_code = 202
    reason = quarantine_reason_for(outcome.memory)
    payload = QuarantineMemoryResponse(
        data=QuarantineMemoryData(
            id=outcome.memory.id,
            status="quarantined",
            lifecycle_revision=outcome.memory.lifecycle_revision,
            pii_detected=outcome.memory.pii_detected,
            quarantine_reason=reason,
        ),
        meta={"message": QUARANTINE_MESSAGES[reason]},
    )
    body = payload.model_dump_json().encode("utf-8")
    await commit_idempotency_fail_closed(
        idem,
        status=202,
        body=body,
        # A quarantine response finalized after a forget must not replay a
        # stale 202; the same lock-and-marker path applies.
        prepare=erased_create_prepare(
            memory_id=outcome.memory.id, org_id=outcome.memory.org_id, body=body
        ),
    )
    return payload


async def finalize_created_response(
    ctx: CreatedResponseContext,
) -> CreateMemoryResponse:
    ctx.response.headers["X-Idempotency-Replayed"] = "false"
    payload = CreateMemoryResponse(
        data=memory_data_from_outcome(ctx.outcome, ctx.org_id),
        meta=CreateMemoryMeta(
            deduplication=DeduplicationMeta(
                is_duplicate=False,
                similar_memories=list(ctx.outcome.near_duplicate_candidates),
            ),
            processing_time_ms=ctx.elapsed_ms,
        ),
    )
    body = payload.model_dump_json().encode("utf-8")
    await commit_idempotency_fail_closed(
        ctx.idem,
        status=201,
        body=body,
        prepare=erased_create_prepare(
            memory_id=ctx.outcome.memory.id, org_id=ctx.org_id, body=body
        ),
    )
    return payload
