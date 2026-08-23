"""FastAPI entrypoint: /health and /ready with startup geometry validation."""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from dataclasses import dataclass

from fastapi import FastAPI, Request, status
from fastapi.responses import JSONResponse

from app.backend import EmbeddingBackend
from app.config import get_settings, load_active_backend
from app.errors import EmbedderError, ServiceNotReadyError

logger = logging.getLogger(__name__)


@dataclass(slots=True)
class AppState:
    backend: EmbeddingBackend | None = None
    ready: bool = False
    ready_error: str | None = None


def _error_response(
    *,
    status_code: int,
    code: str,
    message: str,
) -> JSONResponse:
    return JSONResponse(
        status_code=status_code,
        content={"error": {"code": code, "message": message}},
    )


@asynccontextmanager
async def lifespan(app: FastAPI):
    state = AppState()
    app.state.embedder = state
    settings = get_settings()
    try:
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
    except EmbedderError as exc:
        state.ready = False
        state.ready_error = exc.message if hasattr(exc, "message") else str(exc)
        logger.error(
            "embedder startup geometry validation failed profile=%s error_class=%s",
            settings.profile,
            exc.code,
        )
    except Exception:
        state.ready = False
        state.ready_error = "unexpected startup failure"
        logger.exception("embedder unexpected startup failure profile=%s", settings.profile)
    yield


app = FastAPI(
    title="IBEX Embedder",
    version="0.1.0",
    lifespan=lifespan,
)


def _get_state(request: Request) -> AppState:
    return request.app.state.embedder


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/ready", response_model=None)
async def ready(request: Request):
    state = _get_state(request)
    if not state.ready or state.backend is None:
        message = state.ready_error or "service not ready"
        return _error_response(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            code=ServiceNotReadyError.code,
            message=message,
        )
    backend = state.backend
    return {
        "status": "ready",
        "profile": backend.profile,
        "model_id": backend.model_id,
        "dimensions": backend.dimensions,
        "backend": backend.name,
    }
