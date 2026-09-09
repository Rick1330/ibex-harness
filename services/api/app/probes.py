"""Probe routes for the management API."""

from __future__ import annotations

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse
from prometheus_client import CONTENT_TYPE_LATEST, generate_latest
from starlette.responses import Response

probe_router = APIRouter(tags=["probes"])


@probe_router.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}


@probe_router.get("/ready")
async def ready(request: Request) -> JSONResponse:
    from apierror_py import SERVICE_DEGRADED

    from app.errors import ResponseOpts, envelope_response

    state = getattr(request.app.state, "api", None)
    settings = getattr(request.app.state, "settings", None)
    if state is not None and getattr(state, "ready_error", None):
        return envelope_response(
            code=SERVICE_DEGRADED,
            message=state.ready_error,
            opts=ResponseOpts(settings=settings, status_code=503),
        )
    return JSONResponse({"status": "ready", "service": "api"})


@probe_router.get("/metrics")
async def metrics() -> Response:
    return Response(generate_latest(), media_type=CONTENT_TYPE_LATEST)
