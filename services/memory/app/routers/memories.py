"""Memory write HTTP routes."""

from __future__ import annotations

import hashlib
import time
from typing import Annotated, Any

from fastapi import APIRouter, Depends, Response
from fastapi.responses import JSONResponse

from app.deps import CreateMemoryContext, get_create_memory_context
from app.exceptions import DuplicateMemoryError, EmbeddingServiceError, ValidationError
from app.routers.memory_write_support import (
    CreatedResponseContext,
    begin_idempotency,
    finalize_created_response,
    finalize_quarantine_response,
    http_error_for_write,
    memory_command_from_request,
    release_idempotency,
)
from app.schemas.memories import CreateMemoryRequest
from app.write.models import WriteOutcomeKind

router = APIRouter(prefix="/v1/memories", tags=["memories"])


def _fingerprint(method: str, path: str, body: bytes) -> str:
    digest = hashlib.sha256()
    digest.update(method.upper().encode())
    digest.update(b"\n")
    digest.update(path.encode())
    digest.update(b"\n")
    digest.update(body)
    return digest.hexdigest()


@router.post("", status_code=201, summary="Create a memory")
async def create_memory(
    request: CreateMemoryRequest,
    response: Response,
    ctx: Annotated[CreateMemoryContext, Depends(get_create_memory_context)],
) -> Any:
    start = time.perf_counter()
    body_bytes = request.model_dump_json().encode("utf-8")
    idem = await begin_idempotency(
        store=ctx.idempotency_store,
        org_id=ctx.token.org_id,
        idempotency_key=ctx.idempotency_key,
        fingerprint=_fingerprint("POST", "/v1/memories", body_bytes),
    )
    if isinstance(idem, JSONResponse):
        return idem

    command = memory_command_from_request(request, ctx.token.org_id)
    try:
        outcome = await ctx.orchestrator.create(command)
    except (DuplicateMemoryError, ValidationError, EmbeddingServiceError) as exc:
        await release_idempotency(idem)
        raise http_error_for_write(exc) from exc
    except Exception:
        await release_idempotency(idem)
        raise

    elapsed_ms = int((time.perf_counter() - start) * 1000)
    if outcome.kind == WriteOutcomeKind.QUARANTINED:
        return await finalize_quarantine_response(outcome=outcome, idem=idem, response=response)
    return await finalize_created_response(
        CreatedResponseContext(
            outcome=outcome,
            org_id=ctx.token.org_id,
            elapsed_ms=elapsed_ms,
            idem=idem,
            response=response,
        )
    )
