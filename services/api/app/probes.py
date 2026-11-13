"""Probe routes for the management API."""

from __future__ import annotations

import asyncio

from apierror_py import SERVICE_DEGRADED
from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse
from prometheus_client import CONTENT_TYPE_LATEST, generate_latest
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError
from starlette.responses import Response

from app.errors import ResponseOpts, envelope_response

# One Redis verdict for both surfaces: /v1/operator/platform/health reports the
# same helper's result, so /ready cannot contradict operator SSE readiness.
from app.routers.platform import _redis_status

probe_router = APIRouter(tags=["probes"])

# Mirror packages/healthcheck budgets (overall ~750ms, per-check ~500ms).
_READY_OVERALL_TIMEOUT_S = 0.75
_READY_CHECK_TIMEOUT_S = 0.5


@probe_router.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}


@probe_router.get("/ready")
async def ready(request: Request) -> JSONResponse:
    """Live, per-request dependency checks (Postgres + auth gRPC) — F4-020."""
    # Redis is checked too when configured: it backs the operator SSE fan-in, so
    # a dead Redis is a degraded operator plane. The docstring stays byte-identical
    # because FastAPI publishes it as the OpenAPI operation description.
    state = getattr(request.app.state, "api", None)
    settings = getattr(request.app.state, "settings", None)
    if state is None:
        return envelope_response(
            code=SERVICE_DEGRADED,
            message="api state unavailable",
            opts=ResponseOpts(settings=settings, status_code=503),
        )
    if getattr(state, "drain", None) is not None and state.drain.draining:
        return envelope_response(
            code=SERVICE_DEGRADED,
            message="api is draining",
            opts=ResponseOpts(settings=settings, status_code=503),
        )

    try:
        async with asyncio.timeout(_READY_OVERALL_TIMEOUT_S):
            auth_ok, db_ok, redis_ok = await asyncio.gather(
                _check_auth(state),
                _check_postgres(state),
                _check_redis(settings),
            )
    except TimeoutError:
        return envelope_response(
            code=SERVICE_DEGRADED,
            message="readiness checks timed out",
            opts=ResponseOpts(settings=settings, status_code=503),
        )

    if not auth_ok:
        return envelope_response(
            code=SERVICE_DEGRADED,
            message="auth gRPC not reachable",
            opts=ResponseOpts(settings=settings, status_code=503),
        )
    if not db_ok:
        return envelope_response(
            code=SERVICE_DEGRADED,
            message="database not reachable",
            opts=ResponseOpts(settings=settings, status_code=503),
        )
    if not redis_ok:
        # Operator SSE fan-in reads Redis; a configured-but-down Redis is a
        # degraded operator plane even though request paths still work.
        return envelope_response(
            code=SERVICE_DEGRADED,
            message="redis not reachable",
            opts=ResponseOpts(settings=settings, status_code=503),
        )
    return JSONResponse({"status": "ready", "service": "api"})


async def _check_auth(state: object) -> bool:
    validator = getattr(state, "validator", None)
    if validator is None:
        return False
    try:
        async with asyncio.timeout(_READY_CHECK_TIMEOUT_S):
            return bool(await validator.ready())
    except OSError:
        # TimeoutError is an OSError subclass.
        return False


async def _check_postgres(state: object) -> bool:
    engine = getattr(state, "engine", None)
    if engine is None:
        # No DB configured → not ready for operator/management plane.
        return False
    try:
        async with asyncio.timeout(_READY_CHECK_TIMEOUT_S), engine.connect() as conn:
            await conn.execute(text("SELECT 1"))
        return True
    except (SQLAlchemyError, OSError):
        # TimeoutError is an OSError subclass.
        return False


async def _check_redis(settings: object) -> bool:
    """Redis is optional; when configured it backs operator SSE fan-in."""
    redis_url = getattr(settings, "redis_url", None)
    if not redis_url:
        return True
    try:
        async with asyncio.timeout(_READY_CHECK_TIMEOUT_S):
            return (await _redis_status(redis_url)) == "ok"
    except Exception:  # a probe fails closed on any error, it must never 500
        # TimeoutError is an OSError subclass; a malformed URL raises ValueError.
        return False


@probe_router.get("/metrics")
async def metrics() -> Response:
    return Response(generate_latest(), media_type=CONTENT_TYPE_LATEST)
