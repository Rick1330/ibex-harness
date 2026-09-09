"""FastAPI host for the IBEX management API skeleton (m4.A.1)."""

from __future__ import annotations

import logging
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from dataclasses import dataclass, field

from fastapi import FastAPI
from fastapi.exceptions import RequestValidationError
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.auth.client import GRPCTokenValidator, TokenValidator
from app.config import Settings, get_settings
from app.db import create_engine, create_session_factory
from app.errors import (
    ApiError,
    api_error_handler,
    http_exception_handler,
    request_validation_error_handler,
    unhandled_error_handler,
)
from app.http_metrics import HTTPMetricsMiddleware
from app.middleware.request_id import RequestIdMiddleware
from app.probes import probe_router
from app.routers.tenant import router as tenant_router

logger = logging.getLogger(__name__)


@dataclass
class ApiAppState:
    ready: bool = True
    ready_error: str | None = None
    settings: Settings | None = field(default=None, repr=False)
    engine: AsyncEngine | None = field(default=None, repr=False)
    session_factory: async_sessionmaker[AsyncSession] | None = field(default=None, repr=False)
    validator: TokenValidator | None = field(default=None, repr=False)


def create_app(
    *,
    settings: Settings | None = None,
    validator: TokenValidator | None = None,
) -> FastAPI:
    cfg = settings or get_settings()
    state = ApiAppState(settings=cfg)

    @asynccontextmanager
    async def lifespan(application: FastAPI) -> AsyncGenerator[None, None]:
        async with _api_service_lifespan(state, cfg, validator):
            yield

    application = FastAPI(
        title="IBEX Management API",
        version="0.1.0",
        lifespan=lifespan,
    )
    application.state.api = state
    application.state.settings = cfg
    application.add_exception_handler(ApiError, api_error_handler)
    application.add_exception_handler(RequestValidationError, request_validation_error_handler)
    application.add_exception_handler(StarletteHTTPException, http_exception_handler)
    application.add_exception_handler(Exception, unhandled_error_handler)
    application.include_router(probe_router)
    application.include_router(tenant_router)
    # Request ID outermost so errors and metrics see it; Starlette adds middleware in reverse.
    application.add_middleware(HTTPMetricsMiddleware)
    application.add_middleware(RequestIdMiddleware)
    return application


def _mark_not_ready(state: ApiAppState, message: str) -> None:
    state.ready = False
    state.ready_error = message
    logger.error("api not ready: %s", message)


@asynccontextmanager
async def _api_service_lifespan(
    state: ApiAppState,
    cfg: Settings,
    validator: TokenValidator | None,
) -> AsyncGenerator[None, None]:
    logger.info("api service starting port=%s", cfg.port)
    auth = validator or GRPCTokenValidator(
        cfg.auth_grpc_addr,
        timeout_seconds=cfg.auth_timeout_ms / 1000.0,
    )
    state.validator = auth
    engine: AsyncEngine | None = None

    try:
        if not cfg.database_url:
            _mark_not_ready(state, "IBEX_API_DATABASE_URL not set")
            yield
            return

        engine = create_engine(cfg)
        session_factory = create_session_factory(engine)
        state.engine = engine
        state.session_factory = session_factory
        await _refresh_readiness(state, auth=auth, engine=engine)
        yield
    finally:
        await auth.aclose()
        if engine is not None:
            await engine.dispose()
            logger.info("api service stopped")


async def _refresh_readiness(
    state: ApiAppState,
    *,
    auth: TokenValidator,
    engine: AsyncEngine,
) -> None:
    if not await auth.ready():
        _mark_not_ready(state, "auth gRPC not reachable")
        return
    if not await _postgres_ready(engine):
        _mark_not_ready(state, "database not reachable")
        return
    state.ready = True
    state.ready_error = None


async def _postgres_ready(engine: AsyncEngine) -> bool:
    try:
        async with engine.connect() as conn:
            await conn.execute(text("SELECT 1"))
        return True
    except SQLAlchemyError:
        return False


app = create_app()
