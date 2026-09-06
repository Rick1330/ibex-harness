"""Internal Starlette surface for extraction enqueue (ADR-0072)."""

from __future__ import annotations

import asyncio
import hmac
import json
import logging
import threading
import time
from typing import Any
from uuid import UUID

from starlette.applications import Starlette
from starlette.requests import Request
from starlette.responses import JSONResponse, Response
from starlette.routing import Route

from app.config import Settings, get_settings
from app.extraction.batch import TurnPayload, parse_turns
from app.task_names import TASK_EXTRACT_SESSION_MEMORIES
from app.tasks.extraction import extract_session_memories

logger = logging.getLogger(__name__)

# Slightly above MAX_BATCH_CONTENT_BYTES to allow JSON framing.
MAX_ENQUEUE_BODY_BYTES = 600_000
_DISPATCH_CONCURRENCY = 32
_IDEMPOTENCY_TTL_SEC = 600.0
_IDEMPOTENCY_WAIT_SEC = 30.0
_MAX_IDEMPO_ENTRIES = 10_000

_enqueue_started = False
_enqueue_lock = threading.Lock()
_dispatch_sem = threading.Semaphore(_DISPATCH_CONCURRENCY)
_idempo_lock = threading.Lock()
_idempo: dict[str, _IdempoEntry] = {}


class _IdempoEntry:
    """In-flight (task_id is None) or completed cache entry with waiter event."""

    __slots__ = ("exp", "ready", "task_id")

    def __init__(self, task_id: str | None, exp: float, ready: threading.Event) -> None:
        self.task_id = task_id
        self.exp = exp
        self.ready = ready


class DispatchBusyError(RuntimeError):
    """Raised when enqueue dispatch concurrency is exhausted."""


def _bearer_matches(provided: str, expected: str) -> bool:
    if not expected:
        return False
    a = provided.encode("utf-8")
    b = expected.encode("utf-8")
    if len(a) != len(b):
        return False
    return hmac.compare_digest(a, b)


def _parse_uuid(raw: object, field: str) -> UUID:
    if raw is None:
        raise ValueError(f"{field} is required")
    try:
        return UUID(str(raw))
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{field} must be a UUID") from exc


def _authorize(request: Request, settings: Settings) -> JSONResponse | None:
    expected = ""
    if settings.enqueue_api_token is not None:
        expected = settings.enqueue_api_token.get_secret_value()
    auth = request.headers.get("authorization") or ""
    scheme, _, token = auth.partition(" ")
    if scheme.lower() != "bearer" or not _bearer_matches(token.strip(), expected):
        return JSONResponse({"error": "unauthorized"}, status_code=401)
    return None


def health(_request: Request) -> Response:
    return JSONResponse({"status": "ok"})


def _turns_kwargs(turns: list[TurnPayload]) -> list[dict[str, Any]]:
    return [
        {"turn_index": t.turn_index, "role": t.role, "content": t.content}
        for t in turns
    ]


def _parse_enqueue_body(payload: object) -> dict[str, Any]:
    if not isinstance(payload, dict):
        raise TypeError("invalid_json")
    org_id = _parse_uuid(payload.get("org_id"), "org_id")
    agent_id = _parse_uuid(payload.get("agent_id"), "agent_id")
    session_id = _parse_uuid(payload.get("session_id"), "session_id")
    turns = parse_turns(payload.get("turns"))
    return {
        "org_id": str(org_id),
        "agent_id": str(agent_id),
        "session_id": str(session_id),
        "turns": _turns_kwargs(turns),
    }


def _check_content_length(request: Request) -> None:
    raw = request.headers.get("content-length")
    if raw is None:
        return
    try:
        length = int(raw)
    except ValueError as exc:
        raise ValueError("invalid_content_length") from exc
    if length > MAX_ENQUEUE_BODY_BYTES:
        raise ValueError("payload_too_large")


async def _read_json_limited(request: Request) -> object:
    _check_content_length(request)
    body = bytearray()
    async for chunk in request.stream():
        body.extend(chunk)
        if len(body) > MAX_ENQUEUE_BODY_BYTES:
            raise ValueError("payload_too_large")
    if not body:
        return None
    try:
        return json.loads(body)
    except json.JSONDecodeError as exc:
        raise ValueError("invalid_json") from exc


def _idempo_prune_locked(now: float) -> None:
    expired = [k for k, e in _idempo.items() if e.task_id is not None and e.exp < now]
    for key in expired:
        del _idempo[key]
    overflow = len(_idempo) - _MAX_IDEMPO_ENTRIES
    if overflow <= 0:
        return
    completed = sorted(
        ((k, e) for k, e in _idempo.items() if e.task_id is not None),
        key=lambda item: item[1].exp,
    )
    for key, _ in completed[:overflow]:
        del _idempo[key]


def _idempo_begin(key: str) -> tuple[str | None, bool]:
    """Reserve or observe an idempotency key.

    Returns:
      (task_id, False) when a completed entry is ready to return.
      (None, True) when this caller owns dispatch and must complete/fail.
      (None, False) when waiters timed out — caller should return 503.
    """
    deadline = time.monotonic() + _IDEMPOTENCY_WAIT_SEC
    while True:
        wait_ev: threading.Event | None = None
        with _idempo_lock:
            now = time.monotonic()
            _idempo_prune_locked(now)
            entry = _idempo.get(key)
            if entry is not None and entry.task_id is not None and entry.exp >= now:
                return entry.task_id, False
            if entry is not None and entry.task_id is None:
                wait_ev = entry.ready
            else:
                ready = threading.Event()
                _idempo[key] = _IdempoEntry(None, now + _IDEMPOTENCY_TTL_SEC, ready)
                return None, True
        remaining = deadline - time.monotonic()
        if remaining <= 0 or wait_ev is None:
            return None, False
        if not wait_ev.wait(timeout=remaining):
            return None, False


def _idempo_complete(key: str, task_id: str) -> None:
    with _idempo_lock:
        now = time.monotonic()
        entry = _idempo.get(key)
        if entry is None:
            ready = threading.Event()
            ready.set()
            _idempo[key] = _IdempoEntry(task_id, now + _IDEMPOTENCY_TTL_SEC, ready)
        else:
            entry.task_id = task_id
            entry.exp = now + _IDEMPOTENCY_TTL_SEC
            entry.ready.set()
        _idempo_prune_locked(now)


def _idempo_fail(key: str) -> None:
    with _idempo_lock:
        entry = _idempo.pop(key, None)
        if entry is not None:
            entry.ready.set()


def _idempo_get(key: str) -> str | None:
    """Return a completed cached task id, if present (test/helper)."""
    with _idempo_lock:
        now = time.monotonic()
        _idempo_prune_locked(now)
        entry = _idempo.get(key)
        if entry is None or entry.task_id is None or entry.exp < now:
            return None
        return entry.task_id


def _idempo_put(key: str, task_id: str) -> None:
    """Store a completed task id (test/helper; refreshes TTL)."""
    _idempo_complete(key, task_id)


def _dispatch_extract(request: Request, kwargs: dict[str, Any]) -> str:
    apply_async = getattr(request.app.state, "apply_async", None)
    if apply_async is None:
        result = extract_session_memories.apply_async(kwargs=kwargs)
    else:
        result = apply_async(kwargs)
    return str(getattr(result, "id", None) or result)


async def _dispatch_extract_bounded(request: Request, kwargs: dict[str, Any]) -> str:
    if not _dispatch_sem.acquire(blocking=False):
        raise DispatchBusyError("dispatch_busy")
    try:
        return await asyncio.to_thread(_dispatch_extract, request, kwargs)
    finally:
        _dispatch_sem.release()


def _bad_request(exc: Exception) -> JSONResponse:
    msg = str(exc)
    if msg in {"invalid_json", "payload_too_large", "invalid_content_length"}:
        return JSONResponse({"error": msg}, status_code=400)
    return JSONResponse({"error": msg}, status_code=400)


def _idempotency_key(request: Request, kwargs: dict[str, Any]) -> str:
    header = (request.headers.get("idempotency-key") or "").strip()
    if header:
        return header
    return str(kwargs.get("session_id") or "")


async def enqueue_extraction(request: Request) -> Response:
    settings: Settings = request.app.state.settings
    if denied := _authorize(request, settings):
        return denied
    try:
        payload = await _read_json_limited(request)
        kwargs = _parse_enqueue_body(payload)
    except (ValueError, TypeError) as exc:
        return _bad_request(exc)

    idem_key = _idempotency_key(request, kwargs)
    owner = False
    if idem_key:
        existing, owner = await asyncio.to_thread(_idempo_begin, idem_key)
        if existing is not None:
            return JSONResponse({"task_id": existing}, status_code=202)
        if not owner:
            return JSONResponse({"error": "unavailable"}, status_code=503)

    try:
        task_id = await _dispatch_extract_bounded(request, kwargs)
    except DispatchBusyError:
        if owner and idem_key:
            await asyncio.to_thread(_idempo_fail, idem_key)
        return JSONResponse({"error": "unavailable"}, status_code=503)
    except Exception:
        if owner and idem_key:
            await asyncio.to_thread(_idempo_fail, idem_key)
        logger.exception("worker_enqueue_dispatch_failed")
        return JSONResponse({"error": "unavailable"}, status_code=503)

    if owner and idem_key:
        await asyncio.to_thread(_idempo_complete, idem_key, task_id)
    return JSONResponse({"task_id": task_id}, status_code=202)


def create_enqueue_app(
    settings: Settings | None = None,
    *,
    apply_async: Any | None = None,
) -> Starlette:
    app = Starlette(
        routes=[
            Route("/health", health, methods=["GET"]),
            Route("/internal/extraction/enqueue", enqueue_extraction, methods=["POST"]),
        ]
    )
    app.state.settings = settings or get_settings()
    app.state.apply_async = apply_async
    app.state.task_name = TASK_EXTRACT_SESSION_MEMORIES
    return app


def _run_uvicorn(settings: Settings) -> None:
    import uvicorn

    app = create_enqueue_app(settings)
    config = uvicorn.Config(
        app,
        host=settings.enqueue_host,
        port=settings.enqueue_port,
        log_level="warning",
        access_log=False,
    )
    uvicorn.Server(config).run()


def start_enqueue_server(settings: Settings) -> None:
    """Start uvicorn for the enqueue app in a daemon thread (idempotent)."""
    global _enqueue_started
    with _enqueue_lock:
        if _enqueue_started:
            return
        token = settings.enqueue_api_token
        if token is None or not token.get_secret_value().strip():
            logger.warning(
                "worker_enqueue_http_disabled",
                extra={"reason": "missing_IBEX_WORKER_ENQUEUE_API_TOKEN"},
            )
            return
        thread = threading.Thread(
            target=_run_uvicorn,
            args=(settings,),
            name="worker-enqueue-http",
            daemon=True,
        )
        thread.start()
        _enqueue_started = True
        logger.info(
            "worker_enqueue_http_ready",
            extra={"enqueue_port": settings.enqueue_port},
        )


def reset_enqueue_http_for_tests() -> None:
    global _enqueue_started
    with _enqueue_lock:
        _enqueue_started = False
    with _idempo_lock:
        _idempo.clear()
