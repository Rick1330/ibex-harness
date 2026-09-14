"""Operator-event SSE routes (4.P.0)."""

from __future__ import annotations

import asyncio
import logging
import time
from collections.abc import AsyncIterator
from dataclasses import dataclass

from apierror_py import INVALID_TOKEN, SERVICE_DEGRADED
from fastapi import APIRouter, Request
from fastapi.responses import StreamingResponse
from starlette.responses import JSONResponse, Response

from app.config import Settings
from app.drain import DrainState
from app.errors import ApiError
from app.session_stub import SESSION_KIND_ACCESS, SessionStubError, verify_token
from app.sse.operator_events import SSE_SLOW_WRITES, SSE_WRITE_SECONDS, OperatorSSEHub

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/v1/operator/events", tags=["operator-events"])


@dataclass(frozen=True, slots=True)
class _StreamCtx:
    request: Request
    hub: OperatorSSEHub
    drain: DrainState
    settings: Settings
    last_id: int | None


def _settings(request: Request) -> Settings:
    return request.app.state.settings


async def _require_session(request: Request) -> None:
    settings = _settings(request)
    if not settings.operator_feature_enabled:
        raise ApiError(code=SERVICE_DEGRADED, message="operator feature disabled")
    secret = settings.jwt_hmac_secret
    if not secret:
        raise ApiError(code=SERVICE_DEGRADED, message="session signing secret not configured")
    raw = request.cookies.get(settings.dashboard_session_cookie_name)
    if not raw:
        raise ApiError(code=INVALID_TOKEN, message="missing session cookie")
    try:
        verify_token(
            raw,
            secret=secret,
            issuer=settings.jwt_issuer,
            audience=settings.jwt_audience,
            expect_kind=SESSION_KIND_ACCESS,
        )
    except SessionStubError as exc:
        raise ApiError(code=INVALID_TOKEN, message=str(exc)) from exc


def _parse_last_event_id(request: Request) -> int | None:
    last_raw = request.headers.get("Last-Event-ID")
    if last_raw and last_raw.strip().isdigit():
        return int(last_raw.strip())
    return None


def _draining_response() -> JSONResponse:
    return JSONResponse(
        {"error": {"code": "draining", "message": "api is draining"}},
        status_code=503,
        headers={"X-IBEX-Drain": "1"},
    )


def _observe_write(elapsed: float, settings: Settings) -> None:
    SSE_WRITE_SECONDS.observe(elapsed)
    if elapsed * 1000 >= settings.sse_slow_write_ms:
        SSE_SLOW_WRITES.inc()


async def _event_stream(ctx: _StreamCtx) -> AsyncIterator[bytes]:
    task = asyncio.current_task()
    if task is not None:
        await ctx.drain.register_sse(task)
    try:
        async for chunk in ctx.hub.subscribe(ctx.last_id):
            if await ctx.request.is_disconnected():
                break
            t0 = time.perf_counter()
            try:
                async with asyncio.timeout(ctx.settings.sse_write_deadline_seconds):
                    yield chunk
            except TimeoutError:
                logger.warning("operator sse write deadline exceeded; closing stream")
                break
            _observe_write(time.perf_counter() - t0, ctx.settings)
    except asyncio.CancelledError:
        raise
    except Exception:
        logger.exception("operator sse stream failed")
        raise


def _hub_or_503(request: Request) -> OperatorSSEHub:
    hub: OperatorSSEHub | None = getattr(request.app.state, "operator_sse_hub", None)
    if hub is None:
        raise ApiError(code=SERVICE_DEGRADED, message="operator SSE hub not initialized")
    return hub


@router.get("/stream", response_model=None)
async def stream_events(request: Request) -> Response:
    await _require_session(request)
    settings = _settings(request)
    hub = _hub_or_503(request)
    drain = request.app.state.api.drain
    if drain.draining:
        return _draining_response()
    ctx = _StreamCtx(
        request=request,
        hub=hub,
        drain=drain,
        settings=settings,
        last_id=_parse_last_event_id(request),
    )
    return StreamingResponse(
        _event_stream(ctx),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


@router.post("/publish-test")
async def publish_test_event(request: Request) -> dict[str, object]:
    """Test helper: enqueue one operator event (requires session + CSRF)."""
    await _require_session(request)
    hub = _hub_or_503(request)
    body = await request.json()
    if not isinstance(body, dict):
        body = {"value": body}
    event_id = await hub.publish(body)
    return {"status": "ok", "event_id": event_id}
