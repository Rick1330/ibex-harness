"""FastAPI application: lifespan startup, probe endpoints, and /v1/embed API."""

from __future__ import annotations

import asyncio
import logging
import time
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request, status
from fastapi.responses import JSONResponse
from pydantic import ValidationError

from app.api.embed import embed_router
from app.api.probes import probe_router
from app.backends.tei import TEIBackend
from app.config import get_settings
from app.errors import (
    AuthenticationError,
    BackendUnavailableError,
    EmbedderError,
    GeometryMismatchError,
)
from app.factory import build_backend
from app.schemas import ErrorEnvelope
from app.state import AppState
from app.validate import validate_geometry

logger = logging.getLogger(__name__)

# Interval between /health polls during TEI startup wait.
_HEALTH_POLL_INTERVAL_SECONDS = 1.0


def _error_response(*, status_code: int, code: str, message: str) -> JSONResponse:
    body = ErrorEnvelope(error={"code": code, "message": message})
    return JSONResponse(status_code=status_code, content=body.model_dump())


async def _wait_for_tei_health(backend: TEIBackend, timeout_seconds: float) -> None:
    """Poll backend.health() until it returns True, or raise after timeout.

    Uses a monotonic deadline to avoid clock skew. Polls at most once per
    _HEALTH_POLL_INTERVAL_SECONDS so we don't hammer a slow-starting TEI pod.
    """
    deadline = time.monotonic() + timeout_seconds
    attempt = 0
    while True:
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            break
        attempt += 1
        if await backend.health(timeout_seconds=remaining):
            logger.info("TEI health OK after %d poll(s)", attempt)
            return
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            break
        await asyncio.sleep(min(_HEALTH_POLL_INTERVAL_SECONDS, remaining))

    raise BackendUnavailableError(
        f"TEI did not become healthy within {timeout_seconds:.0f}s "
        f"(polled {attempt} time(s)) — service will not be marked ready"
    )


async def _verify_tei_geometry(backend: TEIBackend) -> None:
    """Fetch /info and assert model_id matches configured value.

    /info identity is mandatory for readiness. A fetch failure or missing model_id
    means we cannot prove the running backend matches configured geometry.
    """
    info = await backend.info()

    remote_model = backend.model_id_from_info(info)
    if remote_model is None:
        raise BackendUnavailableError("TEI /info did not return model_id; refusing readiness")
    if remote_model != backend.model_id:
        raise GeometryMismatchError(
            f"TEI model mismatch: running model_id={remote_model!r} "
            f"but configured model_id={backend.model_id!r}"
        )
    logger.info("TEI model_id confirmed model_id=%s", remote_model)


async def _startup(state: AppState) -> None:
    """Build backend, run TEI startup checks, validate geometry, mark ready."""
    settings = get_settings()
    settings.validate_runtime_security()
    backend = build_backend(settings)

    # Assign backend before health wait so /health probe still responds 200
    # (readiness is separate from liveness).
    state.backend = backend

    if isinstance(backend, TEIBackend):
        await _wait_for_tei_health(backend, settings.tei_health_timeout_seconds)
        await _verify_tei_geometry(backend)

    want_dim, want_model = settings.resolved_geometry()
    validate_geometry(backend, want_dim, want_model)

    state.ready = True
    logger.info(
        "embedder ready profile=%s model_id=%s dimensions=%d backend=%s",
        settings.profile,
        backend.model_id,
        backend.dimensions,
        backend.name,
    )


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    state = AppState()
    app.state.embedder = state
    profile = "unknown"
    try:
        profile = get_settings().profile
        await _startup(state)
    except EmbedderError as exc:
        state.ready = False
        state.ready_error = exc.message
        logger.exception(
            "embedder startup failed profile=%s error_class=%s",
            profile,
            exc.code,
        )
    except (ValidationError, ValueError, TypeError) as exc:
        state.ready = False
        state.ready_error = str(exc) or "invalid startup configuration"
        logger.exception("embedder startup configuration error profile=%s", profile)

    yield

    # Shutdown: release TEI connection pool before process exits.
    if isinstance(state.backend, TEIBackend):
        await state.backend.aclose()
        logger.info("TEI HTTP client closed")


def create_app() -> FastAPI:
    application = FastAPI(
        title="IBEX Embedder",
        version="0.2.0",
        lifespan=lifespan,
    )

    @application.exception_handler(AuthenticationError)
    async def _authentication_error_handler(_: Request, exc: AuthenticationError) -> JSONResponse:
        return _error_response(
            status_code=status.HTTP_401_UNAUTHORIZED,
            code=exc.code,
            message=exc.message,
        )

    @application.exception_handler(EmbedderError)
    async def _embedder_error_handler(_: Request, exc: EmbedderError) -> JSONResponse:
        return _error_response(status_code=503, code=exc.code, message=exc.message)

    application.include_router(probe_router)
    application.include_router(embed_router)
    return application


app = create_app()
