"""HTTP helpers for POST /v1/memories (idempotency + error mapping).

Idempotency is enforced by the shared PostgreSQL ledger
(``ibex_idempotency`` / ``request-idempotency-core.v1``), scoped to
``(organization_id, agent_id, dedupe_key)``. The previous Redis store is gone:
when the caller supplies ``X-Idempotency-Key`` the endpoint either admits the
claim, replays the stored response, or fails closed with 503 — it never writes
without dedupe.
"""

from __future__ import annotations

import asyncio
import json
import logging
import random
from dataclasses import dataclass
from uuid import UUID

from fastapi import HTTPException, Response
from fastapi.responses import JSONResponse
from ibex_idempotency import (
    KIND_CONFLICT,
    KIND_IN_PROGRESS,
    KIND_REPLAY,
    ClaimOutcome,
    ClaimToken,
    LedgerConflictError,
    LedgerError,
    LedgerValidationError,
    PostgresIdempotencyLedger,
)

from app.exceptions import (
    DuplicateMemoryError,
    EmbeddingServiceError,
    MemoryOrganizationUnavailableError,
    StaleLifecycleError,
    ValidationError,
)
from app.schemas.limits import MAX_IDEMPOTENCY_KEY_LENGTH
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
from app.write.models import CreateMemoryCommand, WriteOutcome

logger = logging.getLogger(__name__)

# Recoverable finalization: a committed keyed write must not be reported as
# completed while its ledger claim is still open, so retry transient ledger
# outages a bounded number of times before failing closed with 503.
_FINALIZE_ATTEMPTS = 3
_FINALIZE_BACKOFF_SECONDS = 0.05


def _idempotency_unavailable() -> HTTPException:
    return HTTPException(
        status_code=503,
        detail={
            "code": "IDEMPOTENCY_UNAVAILABLE",
            "message": "Idempotency ledger unavailable",
        },
    )


class IdempotencyHandle:
    """Claim state for a single create-memory request."""

    __slots__ = ("claim", "ledger", "request_hash")

    def __init__(
        self,
        *,
        ledger: PostgresIdempotencyLedger | None,
        claim: ClaimToken | None,
        request_hash: str,
    ) -> None:
        self.ledger = ledger
        self.claim = claim
        self.request_hash = request_hash

    @property
    def active(self) -> bool:
        return self.claim is not None and self.ledger is not None


@dataclass(frozen=True, slots=True)
class Principal:
    """Verified tenant + agent identity for a memory write."""

    org_id: UUID
    agent_id: UUID


@dataclass(frozen=True, slots=True)
class ClaimTarget:
    """Identity of a single ledger claim: org + agent + key + request hash."""

    org_id: UUID
    agent_id: UUID
    key: str
    request_hash: str


@dataclass(frozen=True, slots=True)
class CreatedResponseContext:
    outcome: WriteOutcome
    org_id: UUID
    elapsed_ms: int
    idem: IdempotencyHandle
    response: Response


def parse_idempotency_key(raw: str | None) -> str | None:
    """Validate X-Idempotency-Key before it is used in a ledger claim."""
    if raw is None:
        return None
    key = raw.strip()
    if not key:
        return None
    if len(key) > MAX_IDEMPOTENCY_KEY_LENGTH:
        raise HTTPException(
            status_code=400,
            detail={
                "code": "VALIDATION_ERROR",
                "message": (
                    f"X-Idempotency-Key must be at most {MAX_IDEMPOTENCY_KEY_LENGTH} characters"
                ),
            },
        )
    return key


def _replay_cached_response(outcome: ClaimOutcome) -> JSONResponse | None:
    """Return stored response body when this idempotency key already completed."""
    if outcome.kind == KIND_REPLAY and outcome.response is not None:
        return JSONResponse(
            status_code=outcome.status or 200,
            content=json.loads(outcome.response.decode("utf-8")),
            headers={"X-Idempotency-Replayed": "true"},
        )
    return None


def _reject_idempotency_conflict(outcome: ClaimOutcome) -> None:
    """Raise when the same key is reused with a different body or still in flight."""
    if outcome.kind == KIND_CONFLICT:
        raise HTTPException(
            status_code=409,
            detail={
                "code": "IDEMPOTENCY_CONFLICT",
                "message": "Idempotency key reused with different request",
            },
        )
    if outcome.kind == KIND_IN_PROGRESS:
        headers = (
            {"Retry-After": str(outcome.retry_after)} if outcome.retry_after is not None else None
        )
        raise HTTPException(
            status_code=409,
            detail={
                "code": "IDEMPOTENCY_IN_PROGRESS",
                "message": "Request with this idempotency key is in progress",
            },
            headers=headers,
        )


def _finalize_idempotency_claim(
    outcome: ClaimOutcome,
    handle: IdempotencyHandle,
) -> IdempotencyHandle | JSONResponse:
    """Map claim outcome to either a replay response or an active write handle."""
    replay = _replay_cached_response(outcome)
    if replay is not None:
        return replay
    _reject_idempotency_conflict(outcome)
    if outcome.claim is not None:
        handle.claim = outcome.claim
    return handle


async def _claim_idempotency_slot(
    ledger: PostgresIdempotencyLedger,
    target: ClaimTarget,
) -> ClaimOutcome:
    """Atomically claim the idempotency key in PostgreSQL (or fail closed)."""
    try:
        return await ledger.claim(
            org_id=target.org_id,
            agent_id=target.agent_id,
            key=target.key,
            request_hash=target.request_hash,
        )
    except LedgerValidationError as exc:
        logger.warning("idempotency claim rejected error_class=%s", type(exc).__name__)
        raise HTTPException(
            status_code=400,
            detail={"code": "VALIDATION_ERROR", "message": "Invalid agent for memory scope"},
        ) from exc
    except LedgerError as exc:
        logger.warning("idempotency claim unavailable error_class=%s", type(exc).__name__)
        raise _idempotency_unavailable() from exc


async def begin_idempotency(
    *,
    ledger: PostgresIdempotencyLedger | None,
    principal: Principal,
    idempotency_key: str | None,
    request_hash: str,
) -> IdempotencyHandle | JSONResponse:
    """Claim idempotency slot, replay cached result, or return handle for a new write."""
    handle = IdempotencyHandle(ledger=ledger, claim=None, request_hash=request_hash)
    validated_key = parse_idempotency_key(idempotency_key)
    if not validated_key:
        return handle
    if ledger is None:
        raise _idempotency_unavailable()
    handle.ledger = ledger
    outcome = await _claim_idempotency_slot(
        ledger,
        ClaimTarget(
            org_id=principal.org_id,
            agent_id=principal.agent_id,
            key=validated_key,
            request_hash=request_hash,
        ),
    )
    return _finalize_idempotency_claim(outcome, handle)


async def release_idempotency(handle: IdempotencyHandle) -> None:
    if not handle.active:
        return
    try:
        await handle.ledger.release(handle.claim)
    except LedgerError as exc:
        logger.warning("idempotency release failed error_class=%s", type(exc).__name__)


async def commit_idempotency(handle: IdempotencyHandle, *, status: int, body: bytes) -> None:
    if handle.active:
        await handle.ledger.finalize(handle.claim, status=status, response=body)


async def commit_idempotency_fail_closed(
    handle: IdempotencyHandle, *, status: int, body: bytes
) -> None:
    """Finalize a keyed write, retrying transient outages, then fail closed.

    The memory row is committed before this runs. Swallowing a finalize failure
    would return 201/202 over an unfinished claim: the response could not be
    replayed and, after the lease expired, another claim could write a
    duplicate. Retry the transient cases a bounded number of times; if the
    ledger stays unavailable, surface 503 instead of a false success. A lost
    claim (``LedgerConflictError``) is not retryable and fails closed at once.
    """
    if not handle.active:
        return
    last: LedgerError | None = None
    for attempt in range(_FINALIZE_ATTEMPTS):
        try:
            await commit_idempotency(handle, status=status, body=body)
            return
        except LedgerConflictError as exc:
            last = exc
            break
        except LedgerError as exc:
            last = exc
            if attempt + 1 < _FINALIZE_ATTEMPTS:
                # Full jitter over the exponential window so a shared outage
                # does not synchronize every in-flight request onto the retry.
                window = _FINALIZE_BACKOFF_SECONDS * (2**attempt)
                delay = random.uniform(0.0, window)  # nosec B311 - retry jitter
                await asyncio.sleep(delay)
    logger.warning(
        "idempotency finalize failed after successful write error_class=%s",
        type(last).__name__,
    )
    raise _idempotency_unavailable() from last


def http_error_for_write(exc: BaseException) -> HTTPException:
    if isinstance(exc, MemoryOrganizationUnavailableError):
        return HTTPException(
            status_code=409,
            detail={"code": exc.code, "message": exc.message},
        )
    if isinstance(exc, StaleLifecycleError):
        return HTTPException(
            status_code=409,
            detail={"code": exc.code, "message": exc.message},
        )
    if isinstance(exc, DuplicateMemoryError):
        return HTTPException(
            status_code=409,
            detail={
                "code": "DUPLICATE_CONTENT",
                "message": "A memory with identical content already exists",
                "existing_memory_id": str(exc.existing_id),
            },
        )
    if isinstance(exc, ValidationError):
        return HTTPException(
            status_code=400,
            detail={"code": exc.code, "message": exc.message},
        )
    if isinstance(exc, EmbeddingServiceError):
        return HTTPException(
            status_code=503,
            detail={"code": "EMBEDDING_FAILED", "message": "Embedding service unavailable"},
        )
    raise exc


def http_internal_error_for_write() -> HTTPException:
    return HTTPException(
        status_code=500,
        detail={"code": "INTERNAL_ERROR", "message": "Memory write failed"},
    )


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


async def finalize_quarantine_response(
    *,
    outcome: WriteOutcome,
    idem: IdempotencyHandle,
    response: Response,
) -> QuarantineMemoryResponse:
    response.status_code = 202
    payload = QuarantineMemoryResponse(
        data=QuarantineMemoryData(
            id=outcome.memory.id,
            status="quarantined",
            lifecycle_revision=outcome.memory.lifecycle_revision,
        ),
        meta={"message": "Memory quarantined for review due to PII detection"},
    )
    await commit_idempotency_fail_closed(
        idem, status=202, body=payload.model_dump_json().encode("utf-8")
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
    await commit_idempotency_fail_closed(
        ctx.idem, status=201, body=payload.model_dump_json().encode("utf-8")
    )
    return payload
