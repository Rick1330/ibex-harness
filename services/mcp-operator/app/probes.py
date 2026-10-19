"""Probe and discovery routes for the operator gateway."""

from __future__ import annotations

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse
from prometheus_client import CONTENT_TYPE_LATEST, generate_latest
from starlette.responses import Response

from app.config import Settings

probe_router = APIRouter(tags=["probes"])

OPERATOR_SCOPES = ["operator.read", "runs.read", "evidence.read", "budget.read"]


@probe_router.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}


@probe_router.get("/ready")
async def ready(request: Request) -> JSONResponse:
    """Live readiness: re-check Auth gRPC so late auth boot can recover."""
    state = request.app.state.operator
    if not state.enabled:
        return JSONResponse({"status": "ready", "service": "mcp-operator", "enabled": False})
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
            content={"error": {"code": "service_not_ready", "message": state.ready_error}},
        )
    state.ready = True
    state.ready_error = None
    return JSONResponse({"status": "ready", "service": "mcp-operator"})


@probe_router.get("/.well-known/oauth-protected-resource")
async def protected_resource_metadata(request: Request) -> JSONResponse:
    """RFC 9728 Protected Resource Metadata (MCP resource-server discovery)."""
    state = request.app.state.operator
    if not state.enabled:
        return JSONResponse(
            status_code=404,
            content={
                "error": {
                    "code": "not_found",
                    "message": "operator surface disabled",
                }
            },
        )
    settings: Settings = request.app.state.settings
    return JSONResponse(build_protected_resource_metadata(settings))


def build_protected_resource_metadata(settings: Settings) -> dict[str, object]:
    return {
        "resource": settings.resource_url,
        "authorization_servers": [settings.auth_server_url],
        "bearer_methods_supported": ["header"],
        "scopes_supported": list(OPERATOR_SCOPES),
        "resource_documentation": "https://ibexharness.com/docs/adr/0086-mcp-operator-gateway",
    }


@probe_router.get("/metrics")
async def metrics() -> Response:
    return Response(generate_latest(), media_type=CONTENT_TYPE_LATEST)
