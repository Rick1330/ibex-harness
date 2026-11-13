"""Probe routes for the memory service.

``/health`` is liveness. ``/ready`` is a live readiness probe: it re-checks the
dependencies a request needs (auth gRPC, Postgres, and Redis when the hot cache
is configured) on every call, under the same bounded budget as
``services/api/app/probes.py``. A dependency that dies after bootstrap is
therefore reported instead of a startup flag that stopped being true.
"""

from __future__ import annotations

import asyncio
import logging

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse
from prometheus_client import CONTENT_TYPE_LATEST, generate_latest
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncEngine
from starlette.responses import Response

logger = logging.getLogger(__name__)

probe_router = APIRouter(tags=["probes"])

# Mirror packages/healthcheck budgets (overall ~750ms, per-check ~500ms).
_READY_OVERALL_TIMEOUT_S = 0.75
_READY_CHECK_TIMEOUT_S = 0.5


@probe_router.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}


@probe_router.get("/ready")
async def ready(request: Request) -> JSONResponse:
    """Live readiness: bootstrap flag first, then the real dependencies.

    The startup flag stays authoritative as a fast-fail. A process that never
    wired its dependencies must not claim ready because a later probe happens to
    reach one of them; otherwise the answer is per-request.

    A 503 body is ``{"error": {"code": "service_not_ready", "message": ...,
    "dependency": ...}}`` where ``dependency`` is one of ``auth``, ``postgres``,
    ``redis``, ``bootstrap``, ``timeout``, or ``memory``.
    """
    state = getattr(request.app.state, "memory", None)
    if state is None:
        return _not_ready("memory state unavailable", "memory")
    if getattr(state, "ready", True) is False:
        message = getattr(state, "ready_error", None) or "memory service failed to bootstrap"
        return _not_ready(message, "bootstrap")

    try:
        async with asyncio.timeout(_READY_OVERALL_TIMEOUT_S):
            auth_ok, postgres_ok, redis_ok = await asyncio.gather(
                _check_auth(getattr(state, "validator", None)),
                _check_postgres(getattr(state, "engine", None)),
                _check_redis(getattr(state, "redis", None)),
            )
    except TimeoutError:
        # The per-check budget did not settle the overall one; name the budget
        # rather than guessing which dependency hung.
        return _not_ready("readiness checks timed out", "timeout")

    if not auth_ok:
        return _not_ready("auth gRPC not reachable", "auth")
    if not postgres_ok:
        return _not_ready("database not reachable", "postgres")
    if not redis_ok:
        return _not_ready("redis not reachable", "redis")
    return JSONResponse({"status": "ready", "service": "memory"})


def _not_ready(message: str, dependency: str) -> JSONResponse:
    """Stable unready body: ``dependency`` names the check that failed."""
    return JSONResponse(
        status_code=503,
        content={
            "error": {
                "code": "service_not_ready",
                "message": message,
                "dependency": dependency,
            }
        },
    )


async def _check_auth(validator: object | None) -> bool:
    if validator is None:
        return False
    try:
        async with asyncio.timeout(_READY_CHECK_TIMEOUT_S):
            return bool(await validator.ready())  # type: ignore[attr-defined]
    except Exception:  # a probe fails closed on any error, it must never 500
        return False


async def _check_postgres(engine: AsyncEngine | None) -> bool:
    if engine is None:
        # No engine configured means the service never wired persistence.
        return False
    try:
        async with asyncio.timeout(_READY_CHECK_TIMEOUT_S):
            return await postgres_ready(engine)
    except Exception:  # a probe fails closed on any error, it must never 500
        return False


async def _check_redis(client: object | None) -> bool:
    """Redis is optional: unconfigured is ready, configured-but-down is not."""
    if client is None:
        return True
    try:
        async with asyncio.timeout(_READY_CHECK_TIMEOUT_S):
            return bool(await client.ping())  # type: ignore[attr-defined]
    except Exception:  # a probe fails closed on any error, it must never 500
        return False


async def postgres_ready(engine: AsyncEngine) -> bool:
    """Single Postgres readiness implementation, shared with startup refresh."""
    try:
        async with engine.connect() as conn:
            await conn.execute(text("SELECT 1"))
        return True
    except (OSError, SQLAlchemyError) as exc:
        logger.warning(
            "postgres readiness check failed error_class=%s",
            type(exc).__name__,
        )
        return False


@probe_router.get("/metrics")
async def metrics() -> Response:
    return Response(generate_latest(), media_type=CONTENT_TYPE_LATEST)
