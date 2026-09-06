"""Internal Starlette surface for extraction enqueue (ADR-0072)."""

from __future__ import annotations

import hmac
import json
import logging
import threading
from typing import Any
from uuid import UUID

from starlette.applications import Starlette
from starlette.requests import Request
from starlette.responses import JSONResponse, Response
from starlette.routing import Route

from app.config import Settings, get_settings
from app.extraction.batch import parse_turns
from app.task_names import TASK_EXTRACT_SESSION_MEMORIES
from app.tasks.extraction import extract_session_memories

logger = logging.getLogger(__name__)

_enqueue_started = False
_enqueue_lock = threading.Lock()


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


async def health(_request: Request) -> Response:
    return JSONResponse({"status": "ok"})


async def enqueue_extraction(request: Request) -> Response:
    settings: Settings = request.app.state.settings
    if denied := _authorize(request, settings):
        return denied
    try:
        payload = await request.json()
    except (json.JSONDecodeError, TypeError, ValueError):
        return JSONResponse({"error": "invalid_json"}, status_code=400)
    if not isinstance(payload, dict):
        return JSONResponse({"error": "invalid_json"}, status_code=400)
    try:
        org_id = _parse_uuid(payload.get("org_id"), "org_id")
        agent_id = _parse_uuid(payload.get("agent_id"), "agent_id")
        session_id = _parse_uuid(payload.get("session_id"), "session_id")
        turns = parse_turns(payload.get("turns"))
    except ValueError as exc:
        return JSONResponse({"error": str(exc)}, status_code=400)

    kwargs: dict[str, Any] = {
        "org_id": str(org_id),
        "agent_id": str(agent_id),
        "session_id": str(session_id),
        "turns": [
            {
                "turn_index": t.turn_index,
                "role": t.role,
                "content": t.content,
            }
            for t in turns
        ],
    }
    apply_async = getattr(request.app.state, "apply_async", None)
    if apply_async is None:
        result = extract_session_memories.apply_async(kwargs=kwargs)
    else:
        result = apply_async(kwargs)
    task_id = getattr(result, "id", None) or str(result)
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
        import uvicorn

        app = create_enqueue_app(settings)
        config = uvicorn.Config(
            app,
            host=settings.enqueue_host,
            port=settings.enqueue_port,
            log_level="warning",
            access_log=False,
        )
        server = uvicorn.Server(config)
        thread = threading.Thread(target=server.run, name="worker-enqueue-http", daemon=True)
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
