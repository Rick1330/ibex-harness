"""FastAPI application: lifespan startup, probe endpoints, and /v1/embed API."""

from __future__ import annotations

import asyncio
import logging
import time
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from prometheus_client import CONTENT_TYPE_LATEST, generate_latest
from pydantic import ValidationError
from redis.exceptions import RedisError
from starlette.responses import Response

from app.api.embed import embed_router
from app.api.probes import probe_router
from app.backends.hosted import HostedAPIBackend
from app.backends.tei import TEIBackend
from app.cache.backend import CachingEmbeddingBackend
from app.config import get_settings
from app.deps import ServiceAuthDep
from app.errors import (
    AuthenticationError,
    BackendUnavailableError,
    EmbedderError,
    GeometryMismatchError,
    InvalidVectorError,
)
from app.factory import build_backend, unwrap_backend
from app.http_metrics import HTTPMetricsMiddleware
from app.schemas import ErrorEnvelope
from app.state import AppState
from app.tei.protocol import parse_info_dimensions
from app.validate import validate_geometry

logger = logging.getLogger(__name__)
# Interval between /health polls during TEI startup wait.
_HEALTH_POLL_INTERVAL_SECONDS = 1.0
_GEOMETRY_PROBE_TEXT = "ibex-geometry-probe"


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
    """Fail closed unless TEI model_id and observed vector dim match config.

    /info identity is mandatory. Dimension is taken from /info when present,
    then confirmed with a single bounded embed probe (TEI often omits dim).
    """
    info = await backend.info()
    _assert_tei_model_id(backend, info)
    _assert_info_dimensions(backend, info)
    probe = await backend.embed([_GEOMETRY_PROBE_TEXT])
    _assert_probe_dimensions(probe, backend.dimensions, label="TEI")
    logger.info(
        "TEI geometry confirmed model_id=%s dimensions=%d",
        backend.model_id,
        backend.dimensions,
    )


def _assert_tei_model_id(backend: TEIBackend, info: object) -> None:
    remote_model = backend.model_id_from_info(info)  # type: ignore[arg-type]
    if remote_model is None:
        raise BackendUnavailableError("TEI /info did not return model_id; refusing readiness")
    if remote_model != backend.model_id:
        raise GeometryMismatchError(
            f"TEI model mismatch: running model_id={remote_model!r} "
            f"but configured model_id={backend.model_id!r}"
        )


def _assert_info_dimensions(backend: TEIBackend, info: object) -> None:
    reported = parse_info_dimensions(info)
    if reported is not None and reported != backend.dimensions:
        raise GeometryMismatchError(
            f"TEI dimensions mismatch: reported dim={reported} "
            f"configured dimensions={backend.dimensions}"
        )


def _assert_probe_dimensions(probe: object, want: int, *, label: str) -> None:
    shape = getattr(probe, "shape", ())
    if not _probe_shape_matches(shape, want):
        raise GeometryMismatchError(
            f"{label} dimensions mismatch: observed {shape!r} configured dimensions={want}"
        )


def _probe_shape_matches(shape: object, want: int) -> bool:
    if not hasattr(shape, "__len__"):
        return False
    if len(shape) < 2:  # type: ignore[arg-type]
        return False
    return int(shape[-1]) == want  # type: ignore[index]


async def _verify_hosted_geometry(backend: HostedAPIBackend) -> None:
    """Fail closed unless a probe embed matches configured dimensions.

    Hosted providers have no TEI-style /info; a single bounded embed is the
    geometry contract check (Matryoshka / wrong model dims). HostedAPIBackend.embed
    already L2-validates; a dim mismatch surfaces as InvalidVectorError and is
    remapped so startup reports a geometry failure, not a generic vector error.
    """
    try:
        probe = await backend.embed([_GEOMETRY_PROBE_TEXT])
    except InvalidVectorError as exc:
        raise GeometryMismatchError(
            f"hosted dimensions mismatch during startup probe: {exc.message}"
        ) from exc
    _assert_probe_dimensions(probe, backend.dimensions, label="hosted")
    logger.info(
        "hosted geometry confirmed provider=%s model_id=%s dimensions=%d",
        backend.provider,
        backend.model_id,
        backend.dimensions,
    )


async def _startup(state: AppState) -> None:
    """Build backend, run provider startup checks, validate geometry, mark ready."""
    settings = get_settings()
    settings.validate_runtime_security()
    backend = build_backend(settings)

    # Assign backend before health wait so /health probe still responds 200
    # (readiness is separate from liveness).
    state.backend = backend
    inner = unwrap_backend(backend)

    if isinstance(inner, TEIBackend):
        await _wait_for_tei_health(inner, settings.tei_health_timeout_seconds)
        await _verify_tei_geometry(inner)
    elif isinstance(inner, HostedAPIBackend):
        await _verify_hosted_geometry(inner)

    if isinstance(backend, CachingEmbeddingBackend):
        await _verify_cache_redis(backend)

    want_dim, want_model = settings.resolved_geometry()
    validate_geometry(backend, want_dim, want_model)

    state.ready = True
    logger.info(
        "embedder ready profile=%s model_id=%s dimensions=%d backend=%s cache=%s",
        settings.profile,
        backend.model_id,
        backend.dimensions,
        backend.name,
        isinstance(backend, CachingEmbeddingBackend),
    )


async def _verify_cache_redis(backend: CachingEmbeddingBackend) -> None:
    """Fail closed at startup when cache Redis is unreachable (misconfig)."""
    try:
        await backend.ping()
    except (RedisError, OSError, TimeoutError) as exc:
        raise BackendUnavailableError(
            f"embedding cache Redis ping failed: {type(exc).__name__}"
        ) from exc
    logger.info("embedding cache Redis ping OK")


async def _aclose_backend(backend: object) -> None:
    """Close Redis and/or HTTP clients when the backend exposes aclose()."""
    aclose = getattr(backend, "aclose", None)
    if aclose is None:
        return
    await aclose()


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

    if state.backend is not None:
        await _aclose_backend(state.backend)
        logger.info("embedding backend closed backend=%s", state.backend.name)


def create_app() -> FastAPI:
    application = FastAPI(
        title="IBEX Embedder",
        version="0.2.0",
        lifespan=lifespan,
    )
    application.add_middleware(HTTPMetricsMiddleware)

    @application.exception_handler(AuthenticationError)
    async def _authentication_error_handler(_: Request, exc: AuthenticationError) -> JSONResponse:
        return _error_response(
            status_code=status.HTTP_401_UNAUTHORIZED,
            code=exc.code,
            message=exc.message,
        )

    @application.exception_handler(RequestValidationError)
    async def _request_validation_error_handler(
        _: Request, __: RequestValidationError
    ) -> JSONResponse:
        return _error_response(
            status_code=status.HTTP_400_BAD_REQUEST,
            code="invalid_request",
            message="request validation failed",
        )

    @application.exception_handler(EmbedderError)
    async def _embedder_error_handler(_: Request, exc: EmbedderError) -> JSONResponse:
        return _error_response(status_code=503, code=exc.code, message=exc.message)

    application.include_router(probe_router)
    application.include_router(embed_router)

    @application.get("/metrics")
    async def metrics(_auth: ServiceAuthDep) -> Response:
        """Prometheus scrape endpoint — requires Bearer IBEX_EMBEDDING_API_TOKEN."""
        return Response(generate_latest(), media_type=CONTENT_TYPE_LATEST)

    return application


app = create_app()
