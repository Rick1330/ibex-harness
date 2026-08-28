"""Memory write HTTP routes."""

from __future__ import annotations

import hashlib
import time
from typing import Annotated, Any

from fastapi import APIRouter, Depends, Header, Response
from fastapi.responses import JSONResponse

from app.auth.client import ValidateResult
from app.deps import get_idempotency_store, get_write_orchestrator, require_memory_write
from app.exceptions import DuplicateMemoryError, EmbeddingServiceError, ValidationError
from app.routers.memory_write_support import (
    begin_idempotency,
    commit_idempotency,
    http_error_for_write,
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
from app.write.models import CreateMemoryCommand, WriteOutcomeKind
from app.write.orchestrator import MemoryWriteOrchestrator

router = APIRouter(prefix="/v1/memories", tags=["memories"])


def _fingerprint(method: str, path: str, body: bytes) -> str:
    digest = hashlib.sha256()
    digest.update(method.upper().encode())
    digest.update(b"\n")
    digest.update(path.encode())
    digest.update(b"\n")
    digest.update(body)
    return digest.hexdigest()


def _memory_data_from_outcome(
    outcome,
    request: CreateMemoryRequest,
    org_id,
) -> MemoryData:
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
        visibility=request.visibility,
        pinned=request.pinned,
        tags=list(request.tags),
        retrieval_count=memory.retrieval_count,
        usefulness_score=memory.usefulness_score,
        pii_detected=memory.pii_detected,
        session_id=memory.session_id,
        metadata=memory.metadata,
        created_at=memory.created_at,
        updated_at=memory.updated_at,
    )


@router.post("", status_code=201, summary="Create a memory")
async def create_memory(
    request: CreateMemoryRequest,
    response: Response,
    token: Annotated[ValidateResult, Depends(require_memory_write)],
    orchestrator: Annotated[MemoryWriteOrchestrator, Depends(get_write_orchestrator)],
    idempotency_store: Annotated[object | None, Depends(get_idempotency_store)],
    idempotency_key: Annotated[str | None, Header(alias="X-Idempotency-Key")] = None,
) -> Any:
    start = time.perf_counter()
    body_bytes = request.model_dump_json().encode("utf-8")
    fp = _fingerprint("POST", "/v1/memories", body_bytes)
    idem = await begin_idempotency(
        store=idempotency_store,
        org_id=token.org_id,
        idempotency_key=idempotency_key,
        fingerprint=fp,
    )
    if isinstance(idem, JSONResponse):
        return idem

    command = CreateMemoryCommand(
        org_id=token.org_id,
        agent_id=request.agent_id,
        content=request.content,
        category=request.category,
        confidence=request.confidence,
        session_id=request.session_id,
        metadata=request.metadata,
    )

    try:
        outcome = await orchestrator.create(command)
    except (DuplicateMemoryError, ValidationError, EmbeddingServiceError) as exc:
        await release_idempotency(idem)
        raise http_error_for_write(exc) from exc

    elapsed_ms = int((time.perf_counter() - start) * 1000)
    response.headers["X-Idempotency-Replayed"] = "false"

    if outcome.kind == WriteOutcomeKind.QUARANTINED:
        response.status_code = 202
        payload = QuarantineMemoryResponse(
            data=QuarantineMemoryData(id=outcome.memory.id, status="quarantined"),
            meta={"message": "Memory quarantined for review due to PII detection"},
        )
        await commit_idempotency(
            idem, status=202, body=payload.model_dump_json().encode("utf-8")
        )
        return payload

    payload = CreateMemoryResponse(
        data=_memory_data_from_outcome(outcome, request, token.org_id),
        meta=CreateMemoryMeta(
            deduplication=DeduplicationMeta(
                is_duplicate=False,
                similar_memories=list(outcome.near_duplicate_candidates),
            ),
            processing_time_ms=elapsed_ms,
        ),
    )
    await commit_idempotency(
        idem, status=201, body=payload.model_dump_json().encode("utf-8")
    )
    return payload
