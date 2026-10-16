"""Internal Starlette surface for extraction enqueue (ADR-0072)."""

from __future__ import annotations

import asyncio
import hmac
import json
import logging
import threading
from typing import Any
from uuid import UUID

from redis.exceptions import RedisError
from starlette.applications import Starlette
from starlette.requests import Request
from starlette.responses import JSONResponse, Response
from starlette.routing import Route

from app.config import Settings, get_settings
from app.db import create_engine, create_session_factory
from app.extraction.batch import TurnPayload, parse_turns
from app.idempotency_ledger import ClaimOutcome, PostgresIdempotencyLedger, fingerprint_enqueue
from app.task_names import TASK_EXTRACT_SESSION_MEMORIES
from app.tasks.extraction import extract_session_memories

logger = logging.getLogger(__name__)

# Slightly above MAX_BATCH_CONTENT_BYTES to allow JSON framing.
MAX_ENQUEUE_BODY_BYTES = 600_000
_DISPATCH_CONCURRENCY = 32

_enqueue_started = False
_enqueue_lock = threading.Lock()
_dispatch_sem = threading.Semaphore(_DISPATCH_CONCURRENCY)


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


async def ready(request: Request) -> Response:
    """Report readiness only when auth, PostgreSQL ledger, and Redis are available."""
    settings: Settings = request.app.state.settings
    if not _enqueue_auth_ready(settings):
        return JSONResponse({"status": "not_ready"}, status_code=503)
    ledger = getattr(request.app.state, "ledger", None)
    if ledger is None:
        return JSONResponse({"status": "not_ready"}, status_code=503)
    try:
        await asyncio.wait_for(ledger.ping(), timeout=0.5)
    except Exception:
        logger.exception("worker_enqueue_database_not_ready")
        return JSONResponse({"status": "not_ready"}, status_code=503)
    broker_url = _broker_url(settings)
    if not broker_url:
        return JSONResponse({"status": "not_ready"}, status_code=503)
    return await _ping_broker(broker_url)


def _enqueue_auth_ready(settings: Settings) -> bool:
    token = getattr(settings, "enqueue_api_token", None)
    if token is None:
        return False
    return bool(token.get_secret_value().strip())


def _broker_url(settings: Settings) -> str | None:
    resolved = getattr(settings, "resolved_broker_url", None)
    if isinstance(resolved, str) and resolved.strip():
        return resolved
    redis_url = getattr(settings, "redis_url", None)
    if isinstance(redis_url, str) and redis_url.strip():
        return redis_url
    return None


async def _ping_broker(broker_url: str) -> Response:
    client = None
    try:
        from redis.asyncio import Redis

        client = Redis.from_url(broker_url, socket_timeout=0.5)
        await asyncio.wait_for(client.ping(), timeout=0.5)
    except (RedisError, OSError):
        return JSONResponse({"status": "not_ready"}, status_code=503)
    finally:
        if client is not None:
            await client.aclose()
    return JSONResponse({"status": "ready", "service": "worker"})


def _turns_kwargs(turns: list[TurnPayload]) -> list[dict[str, Any]]:
    return [{"turn_index": t.turn_index, "role": t.role, "content": t.content} for t in turns]


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


def _unavailable() -> JSONResponse:
    return JSONResponse({"error": "unavailable"}, status_code=503)


async def _claim_or_response(
    ledger: Any, kwargs: dict[str, Any], idem_key: str
) -> tuple[ClaimOutcome | None, Response | None]:
    try:
        outcome: ClaimOutcome = await ledger.claim(
            org_id=UUID(kwargs["org_id"]),
            agent_id=UUID(kwargs["agent_id"]),
            key=idem_key,
            request_hash=fingerprint_enqueue(kwargs),
        )
    except Exception:
        logger.exception("worker_enqueue_idempotency_claim_failed")
        return None, JSONResponse({"error": "idempotency_unavailable"}, status_code=503)
    if outcome.kind == "replay":
        return None, Response(
            content=outcome.response or b"{}",
            status_code=outcome.status or 202,
            media_type="application/json",
        )
    if outcome.kind == "conflict":
        return None, JSONResponse({"error": "idempotency_conflict"}, status_code=409)
    if outcome.kind == "in_progress":
        return None, JSONResponse(
            {"error": "idempotency_in_progress"},
            status_code=409,
            headers={"Retry-After": str(outcome.retry_after or 1)},
        )
    if outcome.claim is None:
        return None, JSONResponse({"error": "idempotency_unavailable"}, status_code=503)
    return outcome, None


async def _dispatch_and_finalize(
    request: Request, ledger: Any, kwargs: dict[str, Any], outcome: ClaimOutcome
) -> Response:
    try:
        task_id = await _dispatch_extract_bounded(request, kwargs)
    except DispatchBusyError:
        await _release_durable_claim(ledger, outcome)
        return _unavailable()
    except Exception:
        await _release_durable_claim(ledger, outcome)
        logger.exception("worker_enqueue_dispatch_failed")
        return _unavailable()
    body = json.dumps({"task_id": task_id}, separators=(",", ":")).encode("utf-8")
    try:
        await ledger.finalize(outcome.claim, status=202, response=body)
    except Exception:
        logger.exception("worker_enqueue_idempotency_finalize_failed")
        return JSONResponse({"error": "idempotency_unavailable"}, status_code=503)
    return Response(content=body, status_code=202, media_type="application/json")


async def enqueue_extraction(request: Request) -> Response:
    settings: Settings = request.app.state.settings
    if denied := _authorize(request, settings):
        return denied
    try:
        payload = await _read_json_limited(request)
        kwargs = _parse_enqueue_body(payload)
    except (ValueError, TypeError) as exc:
        return _bad_request(exc)

    idem_key = (request.headers.get("idempotency-key") or "").strip()
    if not idem_key:
        return JSONResponse({"error": "idempotency_key_required"}, status_code=400)
    if len(idem_key) > 256:
        return JSONResponse({"error": "idempotency_key_too_long"}, status_code=400)
    ledger = getattr(request.app.state, "ledger", None)
    if ledger is None:
        return JSONResponse({"error": "idempotency_unavailable"}, status_code=503)
    outcome, response = await _claim_or_response(ledger, kwargs, idem_key)
    if response is not None:
        return response
    assert outcome is not None
    return await _dispatch_and_finalize(request, ledger, kwargs, outcome)


async def _release_durable_claim(ledger: Any, outcome: ClaimOutcome) -> None:
    try:
        if outcome.claim is not None:
            await ledger.release(outcome.claim)
    except Exception:
        logger.exception("worker_enqueue_idempotency_release_failed")


def create_enqueue_app(
    settings: Settings | None = None,
    *,
    apply_async: Any | None = None,
    ledger: Any | None = None,
) -> Starlette:
    resolved_settings = settings or get_settings()
    app = Starlette(
        routes=[
            Route("/health", health, methods=["GET"]),
            Route("/ready", ready, methods=["GET"]),
            Route("/internal/extraction/enqueue", enqueue_extraction, methods=["POST"]),
        ]
    )
    app.state.settings = resolved_settings
    app.state.apply_async = apply_async
    if ledger is None and getattr(resolved_settings, "database_url", None):
        engine = create_engine(resolved_settings)
        ledger = PostgresIdempotencyLedger(create_session_factory(engine))
    app.state.ledger = ledger
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
