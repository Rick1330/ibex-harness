"""FastAPI entrypoint: /health and /ready with startup geometry validation."""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager

from fastapi import APIRouter, FastAPI, Request, status
from fastapi.responses import JSONResponse
from pydantic import ValidationError

from app.config import get_settings, load_active_backend
from app.deps import AppStateDep
from app.errors import EmbedderError, ServiceNotReadyError
from app.schemas import ErrorEnvelope, HealthResponse, ReadyResponse
from app.state import AppState

logger = logging.getLogger(__name__)

probe_router = APIRouter(tags=["probes"])


def error_response(*, status_code: int, code: str, message: str) -> JSONResponse:
    body = ErrorEnvelope(error={"code": code, "message": message})
    return JSONResponse(status_code=status_code, content=body.model_dump())


def _startup_embedder(state: AppState) -> None:
    settings = get_settings()
    backend = load_active_backend(settings)
    state.backend = backend
    state.ready = True
    logger.info(
        "embedder ready profile=%s model_id=%s dimensions=%d backend=%s",
        settings.profile,
        backend.model_id,
        backend.dimensions,
        backend.name,
    )


def _mark_startup_failed(state: AppState, message: str) -> None:
    state.ready = False
    state.ready_error = message


@asynccontextmanager
async def lifespan(app: FastAPI):
    state = AppState()
    app.state.embedder = state
    profile = "unknown"
    try:
        settings = get_settings()
        profile = settings.profile
        _startup_embedder(state)
    except EmbedderError as exc:
        _mark_startup_failed(state, exc.message if hasattr(exc, "message") else str(exc))
        logger.exception(
            "embedder startup geometry validation failed profile=%s error_class=%s",
            profile,
            exc.code,
        )
    except (ValidationError, ValueError, TypeError):
        _mark_startup_failed(state, "invalid startup configuration")
        logger.exception(
            "embedder startup configuration error profile=%s",
            profile,
        )
    yield


@probe_router.get("/health")
async def health() -> HealthResponse:
    return HealthResponse()


@probe_router.get("/ready", response_model=None)
async def ready(state: AppStateDep):
    if not state.ready or state.backend is None:
        message = state.ready_error or "service not ready"
        return error_response(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            code=ServiceNotReadyError.code,
            message=message,
        )
    backend = state.backend
    return ReadyResponse(
        profile=backend.profile,
        model_id=backend.model_id,
        dimensions=backend.dimensions,
        backend=backend.name,
    )


def create_app() -> FastAPI:
    application = FastAPI(
        title="IBEX Embedder",
        version="0.1.0",
        lifespan=lifespan,
    )

    @application.exception_handler(EmbedderError)
    async def embedder_error_handler(_request: Request, exc: EmbedderError) -> JSONResponse:
        return error_response(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            code=exc.code,
            message=exc.message if hasattr(exc, "message") else str(exc),
        )

    application.include_router(probe_router)
    return application


app = create_app()
