"""Probe routes for the memory service."""

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
    """Bootstrap readiness: process is up. DB-backed readiness lands with VectorStore."""
    state = getattr(request.app.state, "memory", None)
    if state is not None and getattr(state, "ready_error", None):
        return JSONResponse(
            status_code=503,
            content={
                "error": {
                    "code": "service_not_ready",
                    "message": state.ready_error,
                }
            },
        )
    return JSONResponse({"status": "ready", "service": "memory"})


@probe_router.get("/metrics")
async def metrics() -> Response:
    return Response(generate_latest(), media_type=CONTENT_TYPE_LATEST)
