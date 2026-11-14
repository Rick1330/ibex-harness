"""Memory write HTTP routes."""

from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Annotated, Any
from uuid import UUID

from authclient.permissions import MEMORY_DELETE
from fastapi import APIRouter, Depends, HTTPException, Query, Response
from fastapi.responses import JSONResponse
from ibex_idempotency import IDEMPOTENCY_CONTRACT, fingerprint_request
from sqlalchemy.exc import SQLAlchemyError

from app.auth.client import ValidateResult
from app.cache.hot_keys import HOT_CACHE_CAPACITY
from app.deps import (
    CreateMemoryContext,
    FeedbackMemoryContext,
    HotMemoryContext,
    LineageMemoryContext,
    SearchMemoryContext,
    get_create_memory_context,
    get_feedback_memory_context,
    get_hot_memory_context,
    get_lineage_memory_context,
    get_memory_cache_writer,
    get_search_memory_context,
    get_session_factory,
    require_token,
)
from app.exceptions import EmbeddingServiceError, MemoryNotFoundError, ValidationError
from app.feedback.models import ApplyFeedbackCommand, FeedbackKind
from app.feedback.persist import require_agent_id
from app.lifecycle import ForgetMemory
from app.permissions import has_permission
from app.read.lineage import DEFAULT_LINEAGE_DEPTH, MAX_LINEAGE_DEPTH, LineageQuery
from app.read.models import HotMemoryQuery
from app.routers.memory_lineage_support import lineage_response_from_result
from app.routers.memory_search_support import (
    SearchMemoriesExecution,
    embed_query_text,
    ensure_search_agent_authorized,
    http_error_for_search,
    log_search_database_failure,
    resolve_search_agent_id,
    run_memory_search,
    search_response_from_results,
)
from app.routers.memory_write_support import (
    CreatedResponseContext,
    Principal,
    begin_idempotency,
    create_memory_outcome,
    ensure_write_agent_authorized,
    finalize_created_response,
    finalize_quarantine_response,
    forget_memory_with_error_mapping,
    invalidate_forgotten_memory,
    memory_command_from_request,
    require_agent_scope,
)
from app.schemas.feedback import (
    FeedbackErrorEnvelope,
    RecordFeedbackData,
    RecordFeedbackRequest,
    RecordFeedbackResponse,
)
from app.schemas.lineage import LineageErrorEnvelope, MemoryLineageResponse
from app.schemas.memories import (
    CreateMemoryRequest,
    ForgetMemoryData,
    ForgetMemoryRequest,
    ForgetMemoryResponse,
)
from app.schemas.search import SearchMemoriesRequest, SearchMemoriesResponse
from app.write.models import WriteOutcomeKind

router = APIRouter(prefix="/v1/memories", tags=["memories"])

CREATE_MEMORY_PATH = "/v1/memories"


def require_memory_delete(
    token: Annotated[ValidateResult, Depends(require_token)],
) -> ValidateResult:
    """Require ``memory:delete``; forgetting is destructive, not a write."""
    if not has_permission(token.permissions, MEMORY_DELETE):
        raise HTTPException(
            status_code=403,
            detail={
                "code": "INSUFFICIENT_PERMISSIONS",
                "message": "Permission required: memory:delete",
            },
        )
    return token


@dataclass(frozen=True, slots=True)
class ForgetMemoryContext:
    """Authenticated scope and dependencies for the forget route."""

    token: ValidateResult
    session_factory: Any
    cache_writer: Any


def get_forget_memory_context(
    token: Annotated[ValidateResult, Depends(require_memory_delete)],
    session_factory: Annotated[Any, Depends(get_session_factory)],
    cache_writer: Annotated[Any, Depends(get_memory_cache_writer)],
) -> ForgetMemoryContext:
    return ForgetMemoryContext(
        token=token,
        session_factory=session_factory,
        cache_writer=cache_writer,
    )


@router.post(
    "",
    status_code=201,
    summary="Create a memory",
    responses={
        403: {"description": "Agent-scoped token and a different agent_id"},
        404: {"description": "Agent not found in the caller's organization"},
    },
)
async def create_memory(
    request: CreateMemoryRequest,
    response: Response,
    ctx: Annotated[CreateMemoryContext, Depends(get_create_memory_context)],
) -> Any:
    """Create one memory inside the validated token's organization.

    The tenant is taken from the validated token, never from the request body, so
    a caller cannot choose the org it writes to. An agent-scoped token may only
    write for its own agent; an org-scoped token may write for any agent in its
    org, and the composite ``(agent_id, org_id)`` foreign key turns an unknown
    agent into a 404 instead of a 500. A request carrying an idempotency key
    replays the stored response; a keyed write whose slot cannot be claimed or
    finalized fails with 503 rather than a false 201/202, and a failed write
    releases the slot.
    """
    ensure_write_agent_authorized(ctx.token, request.agent_id)
    start = time.perf_counter()
    idem = await begin_idempotency(
        ledger=ctx.idempotency_ledger,
        principal=Principal(org_id=ctx.token.org_id, agent_id=request.agent_id),
        idempotency_key=ctx.idempotency_key,
        request_hash=fingerprint_request(
            contract=IDEMPOTENCY_CONTRACT,
            method="POST",
            path=CREATE_MEMORY_PATH,
            payload=request.model_dump(mode="json"),
        ),
    )
    if isinstance(idem, JSONResponse):
        return idem

    command = memory_command_from_request(request, ctx.token.org_id)
    outcome = await create_memory_outcome(ctx.orchestrator, command, idem, ctx.token.org_id)
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


@router.post(
    "/{memory_id}/forget",
    summary="Forget a memory",
    responses={
        401: {"description": "Authentication required"},
        403: {"description": "Agent-scoped token and memory:delete permission required"},
        404: {"description": "Memory not found in caller scope"},
        409: {"description": "Expected lifecycle revision is stale"},
        422: {"description": "Invalid memory UUID or expected_revision body"},
        503: {"description": "Authentication or database service unavailable"},
    },
)
async def forget_memory(
    memory_id: UUID,
    request: ForgetMemoryRequest,
    ctx: Annotated[ForgetMemoryContext, Depends(get_forget_memory_context)],
) -> ForgetMemoryResponse:
    """Tombstone a memory in the authenticated token's org and agent scope.

    Forget is destructive (erasure, not a visibility toggle), so it requires
    ``memory:delete`` rather than the write permission that creates memories.
    """
    agent_id = require_agent_scope(ctx.token)
    revision = await forget_memory_with_error_mapping(
        session_factory=ctx.session_factory,
        command=ForgetMemory(
            org_id=ctx.token.org_id,
            agent_id=agent_id,
            memory_id=memory_id,
            expected_revision=request.expected_revision,
        ),
    )
    await invalidate_forgotten_memory(
        ctx.cache_writer,
        org_id=ctx.token.org_id,
        agent_id=agent_id,
        memory_id=memory_id,
    )
    return ForgetMemoryResponse(
        data=ForgetMemoryData(memory_id=memory_id, revision=revision, tombstoned=True)
    )


@router.post("/search", summary="Semantic search over memories")
async def search_memories(
    request: SearchMemoriesRequest,
    ctx: Annotated[SearchMemoryContext, Depends(get_search_memory_context)],
) -> SearchMemoriesResponse:
    agent_id = resolve_search_agent_id(ctx.token, request.agent_id)
    try:
        await ensure_search_agent_authorized(
            ctx.session_factory,
            org_id=ctx.token.org_id,
            agent_id=agent_id,
        )
        embedding = await embed_query_text(
            ctx.embedding_client,
            org_id=ctx.token.org_id,
            query=request.query,
        )
        results = await run_memory_search(
            ctx.read_repository,
            SearchMemoriesExecution.from_request(
                org_id=ctx.token.org_id,
                agent_id=agent_id,
                request=request,
                query_embedding=embedding,
            ),
        )
    except (EmbeddingServiceError, ValueError) as exc:
        raise http_error_for_search(exc) from exc
    except SQLAlchemyError as exc:
        log_search_database_failure(exc, org_id=ctx.token.org_id)
        raise http_error_for_search(exc) from exc
    return search_response_from_results(results)


@router.get("/hot", summary="List hot-cache memories for an agent")
async def list_hot_memories(
    ctx: Annotated[HotMemoryContext, Depends(get_hot_memory_context)],
    agent_id: Annotated[UUID, Query()],
    limit: Annotated[int, Query(ge=1, le=HOT_CACHE_CAPACITY)] = 20,
    min_confidence: Annotated[float, Query(ge=0.0, le=1.0)] = 0.0,
) -> SearchMemoriesResponse:
    """Expose MemoryHotCacheReader over HTTP for context assembly (3.5.C.2).

    Response shape matches POST /v1/memories/search so assemblers can treat
    hot and cold hits uniformly (``source=hot_cache``).
    """
    resolved_agent_id = resolve_search_agent_id(ctx.token, agent_id)
    try:
        await ensure_search_agent_authorized(
            ctx.session_factory,
            org_id=ctx.token.org_id,
            agent_id=resolved_agent_id,
        )
        results = await ctx.hot_cache_reader.get_hot_memories(
            HotMemoryQuery(
                org_id=ctx.token.org_id,
                agent_id=resolved_agent_id,
                limit=limit,
                min_confidence=min_confidence,
                suppress_conflicts=ctx.settings.conflict_suppression_enabled,
            )
        )
    except ValueError as exc:
        raise http_error_for_search(exc) from exc
    except SQLAlchemyError as exc:
        log_search_database_failure(exc, org_id=ctx.token.org_id)
        raise http_error_for_search(exc) from exc
    return search_response_from_results(results)


@router.get(
    "/{memory_id}/lineage",
    summary="Read the bounded relationship lineage of a memory",
    responses={
        404: {
            "model": LineageErrorEnvelope,
            "description": "Memory not visible to this organization and agent",
        },
        503: {
            "model": LineageErrorEnvelope,
            "description": "Database unavailable while walking the relationship graph",
        },
    },
)
async def read_memory_lineage(
    memory_id: UUID,
    ctx: Annotated[LineageMemoryContext, Depends(get_lineage_memory_context)],
    max_depth: Annotated[int, Query(ge=1, le=MAX_LINEAGE_DEPTH)] = DEFAULT_LINEAGE_DEPTH,
) -> MemoryLineageResponse:
    """Walk typed relationship edges from one memory, in both directions.

    The depth cap and the cycle break are part of the traversal query, so no
    request can ask for an unbounded walk. An agent-scoped token only sees
    memories belonging to its own agent, and a memory outside the token
    organization is a plain 404 -- making "wrong tenant" distinguishable from
    "does not exist" would be an existence leak, not a UX improvement.
    """
    try:
        result = await ctx.lineage_repository.get_lineage(
            LineageQuery(
                org_id=ctx.token.org_id,
                memory_id=memory_id,
                agent_id=ctx.token.agent_id,
                max_depth=max_depth,
            )
        )
    except ValueError as exc:
        raise http_error_for_search(exc) from exc
    except SQLAlchemyError as exc:
        log_search_database_failure(exc, org_id=ctx.token.org_id)
        raise http_error_for_search(exc) from exc
    if result is None:
        raise HTTPException(
            status_code=404,
            detail={"code": "NOT_FOUND", "message": "Memory not found"},
        )
    return lineage_response_from_result(result)


@router.post(
    "/{memory_id}/feedback",
    summary="Record usefulness feedback for a memory",
    responses={
        400: {
            "model": FeedbackErrorEnvelope,
            "description": "Validation error (missing agent scope or invalid body)",
        },
        404: {
            "model": FeedbackErrorEnvelope,
            "description": "Memory not found in the caller's organization",
        },
        503: {
            "model": FeedbackErrorEnvelope,
            "description": "Database unavailable while applying feedback",
        },
    },
)
async def record_memory_feedback(
    memory_id: UUID,
    request: RecordFeedbackRequest,
    ctx: Annotated[FeedbackMemoryContext, Depends(get_feedback_memory_context)],
) -> RecordFeedbackResponse:
    try:
        agent_id = require_agent_id(ctx.token.agent_id)
        result = await ctx.feedback_service.apply(
            ApplyFeedbackCommand(
                org_id=ctx.token.org_id,
                agent_id=agent_id,
                memory_id=memory_id,
                feedback=FeedbackKind(request.feedback),
                session_id=request.session_id,
                trace_id=request.trace_id,
                notes=request.notes,
            )
        )
    except (MemoryNotFoundError, ValidationError) as exc:
        raise http_error_for_feedback(exc) from exc
    except SQLAlchemyError as exc:
        raise http_error_for_feedback_database(exc) from exc
    return RecordFeedbackResponse(
        data=RecordFeedbackData(
            memory_id=result.memory_id,
            feedback=result.feedback.value,  # type: ignore[arg-type]
            new_usefulness_score=result.new_usefulness_score,
            total_positive_feedback=result.total_positive_feedback,
            total_negative_feedback=result.total_negative_feedback,
        )
    )


def http_error_for_feedback(exc: BaseException) -> HTTPException:
    if isinstance(exc, MemoryNotFoundError):
        return HTTPException(
            status_code=404,
            detail={"code": "NOT_FOUND", "message": "Memory not found"},
        )
    if isinstance(exc, ValidationError):
        return HTTPException(
            status_code=400,
            detail={"code": exc.code, "message": exc.message},
        )
    raise exc


def http_error_for_feedback_database(_exc: BaseException) -> HTTPException:
    """Map SQLAlchemy failures to a stable 503 envelope (documented in responses)."""
    return HTTPException(
        status_code=503,
        detail={"code": "DATABASE_UNAVAILABLE", "message": "Database unavailable"},
    )
