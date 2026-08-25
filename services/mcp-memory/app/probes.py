"""Probe and discovery routes."""

from __future__ import annotations

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse
from prometheus_client import CONTENT_TYPE_LATEST, generate_latest
from starlette.responses import Response

from app.config import Settings

probe_router = APIRouter(tags=["probes"])


@probe_router.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}


@probe_router.get("/ready")
async def ready(request: Request) -> JSONResponse:
    state = request.app.state.mcp
    if not state.ready:
        return JSONResponse(
            status_code=503,
            content={
                "error": {
                    "code": "service_not_ready",
                    "message": state.ready_error or "service not ready",
                }
            },
        )
    return JSONResponse({"status": "ready", "service": "mcp-memory"})


@probe_router.get("/.well-known/oauth-protected-resource")
async def protected_resource_metadata(request: Request) -> dict[str, object]:
    settings: Settings = request.app.state.settings
    return {
        "resource": settings.resource_url,
        "authorization_servers": [settings.auth_server_url],
        "bearer_methods_supported": ["header"],
        "scopes_supported": ["memory:read", "memory:write"],
        "resource_documentation": "https://ibexharness.com/docs/adr/0050-mcp-server-skeleton",
    }


@probe_router.get("/metrics")
async def metrics() -> Response:
    return Response(generate_latest(), media_type=CONTENT_TYPE_LATEST)
