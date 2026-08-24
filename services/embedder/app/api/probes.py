"""GET /health and GET /ready probe endpoints."""

from __future__ import annotations

from fastapi import APIRouter, status
from fastapi.responses import JSONResponse

from app.deps import AppStateDep
from app.errors import ServiceNotReadyError
from app.schemas import ErrorEnvelope, HealthResponse, ReadyResponse

probe_router = APIRouter(tags=["probes"])


def _error_json(*, status_code: int, code: str, message: str) -> JSONResponse:
    body = ErrorEnvelope(error={"code": code, "message": message})
    return JSONResponse(status_code=status_code, content=body.model_dump())


@probe_router.get("/health")
async def health() -> HealthResponse:
    return HealthResponse()


@probe_router.get("/ready", response_model=None)
async def ready(state: AppStateDep) -> ReadyResponse | JSONResponse:
    if not state.ready or state.backend is None:
        message = state.ready_error or "service not ready"
        return _error_json(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            code=ServiceNotReadyError.code,
            message=message,
        )
    backend = state.backend
    return ReadyResponse(
        profile=backend.profile,
        model_id=backend.model_id,
        dimensions=backend.dimensions,
        backend=backend.name,
    )
