"""POST /v1/embed — internal embedding endpoint (Bearer service token)."""

from __future__ import annotations

import logging

from fastapi import APIRouter, status
from fastapi.responses import JSONResponse

from app.cache.context import org_context
from app.deps import AppStateDep, ServiceAuthDep
from app.errors import (
    BackendRejectedError,
    BackendTimeoutError,
    BackendUnavailableError,
    BatchTooLargeError,
    EmptyBatchError,
    InvalidVectorError,
    MissingOrgContextError,
    ServiceNotReadyError,
    TextTooLongError,
)
from app.schemas import EmbedRequest, EmbedResponse, ErrorEnvelope

logger = logging.getLogger(__name__)

embed_router = APIRouter(prefix="/v1", tags=["embed"])

_VALIDATION_ERRORS = (
    EmptyBatchError,
    BatchTooLargeError,
    TextTooLongError,
    BackendRejectedError,
    MissingOrgContextError,
)


def _error_json(*, status_code: int, code: str, message: str) -> JSONResponse:
    body = ErrorEnvelope(error={"code": code, "message": message})
    return JSONResponse(status_code=status_code, content=body.model_dump())


@embed_router.post("/embed", response_model=EmbedResponse, response_model_exclude_none=True)
async def embed(
    request: EmbedRequest,
    _auth: ServiceAuthDep,
    state: AppStateDep,
) -> EmbedResponse | JSONResponse:
    """Embed a batch of texts and return L2-normalized float32 vectors.

    Returns 503 when the backend is not ready or the upstream is unavailable.
    Returns 400 for validation failures (empty batch, oversized texts, etc.).
    Internal endpoint protected by a service Bearer token.
    ``org_id`` is required for tenant-scoped embedding cache keys.
    """
    if not state.ready or state.backend is None:
        message = state.ready_error or "service not ready"
        return _error_json(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            code=ServiceNotReadyError.code,
            message=message,
        )

    with org_context(request.org_id):
        try:
            vectors = await state.backend.embed(request.texts)
        except _VALIDATION_ERRORS as exc:
            logger.warning("embed validation/rejection error_class=%s", type(exc).__name__)
            return _error_json(
                status_code=status.HTTP_400_BAD_REQUEST,
                code=exc.code,
                message=exc.message,
            )
        except InvalidVectorError as exc:
            logger.exception(
                "embed invalid upstream vectors error_class=%s", type(exc).__name__
            )
            return _error_json(
                status_code=status.HTTP_502_BAD_GATEWAY,
                code=exc.code,
                message=exc.message,
            )
        except (BackendUnavailableError, BackendTimeoutError) as exc:
            logger.exception("embed backend error error_class=%s", type(exc).__name__)
            return _error_json(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                code=exc.code,
                message=exc.message,
            )

    backend = state.backend
    return EmbedResponse(
        vectors=vectors.tolist(),
        model_id=backend.model_id,
        dimensions=backend.dimensions,
        backend=backend.name,
    )
