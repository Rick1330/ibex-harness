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
    """Live readiness: re-check Auth gRPC so late auth boot can recover."""
    state = request.app.state.mcp
    validator = state.validator
    if validator is None:
        return JSONResponse(
            status_code=503,
            content={
                "error": {
                    "code": "service_not_ready",
                    "message": "auth validator not initialized",
                }
            },
        )
    if not await validator.ready():
        state.ready = False
        state.ready_error = "auth gRPC not reachable"
        return JSONResponse(
            status_code=503,
            content={
                "error": {
                    "code": "service_not_ready",
                    "message": state.ready_error,
                }
            },
        )
    state.ready = True
    state.ready_error = None
    return JSONResponse({"status": "ready", "service": "mcp-memory"})


@probe_router.get("/.well-known/oauth-protected-resource")
async def protected_resource_metadata(request: Request) -> dict[str, object]:
    """RFC 9728 Protected Resource Metadata (MCP resource-server discovery).

    IBEX ships the minimum discovery fields MCP clients need to locate the
    authorization server and understand scopes for this resource. Exhaustive
    RFC 9728 field completeness is deferred (tracked as an E.1 follow-up).
    """
    settings: Settings = request.app.state.settings
    return build_protected_resource_metadata(settings)


def build_protected_resource_metadata(settings: Settings) -> dict[str, object]:
    """Build the PRM JSON document for ``IBEX_MCP_RESOURCE_URL``.

    Minimum fields (locked for 3.5.E.1): ``resource``, ``authorization_servers``,
    ``scopes_supported``. ``bearer_methods_supported`` and
    ``resource_documentation`` are additive discovery hints.
    """
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
