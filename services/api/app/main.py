"""FastAPI host for the IBEX management API (m4.A.1 + m4.A.2)."""

from __future__ import annotations

import logging
from collections.abc import AsyncGenerator, Callable
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
from app.logutil import install_request_id_log_filter, request_id_for_log
from app.middleware.request_id import RequestIdMiddleware
from app.probes import probe_router
from app.revocation_publish import (
    NoopOrgSuspendPublisher,
    OrgSuspendPublisher,
    RedisOrgSuspendPublisher,
)
from app.routers.agents import router as agents_router
from app.routers.organizations import router as organizations_router
from app.routers.providers import router as providers_router
from app.routers.tenant import router as tenant_router
from app.routers.tokens import router as tokens_router
from app.routers.users import router as users_router

logger = logging.getLogger(__name__)
install_request_id_log_filter(logger)


@dataclass
class ApiRuntimeOverrides:
    """Optional test/runtime wiring for revokers, publishers, and enqueue hooks."""

    token_revoker: object | None = None
    token_manager: object | None = None
    provider_credential_manager: object | None = None
    org_suspend_publisher: OrgSuspendPublisher | None = None
    enqueue_org_deletion: Callable[[str, str], None] | None = None


@dataclass
class ApiAppState:
    ready: bool = True
    ready_error: str | None = None
    settings: Settings | None = field(default=None, repr=False)
    engine: AsyncEngine | None = field(default=None, repr=False)
    session_factory: async_sessionmaker[AsyncSession] | None = field(default=None, repr=False)
    validator: TokenValidator | None = field(default=None, repr=False)
    token_revoker: object | None = field(default=None, repr=False)
    token_manager: object | None = field(default=None, repr=False)
    provider_credential_manager: object | None = field(default=None, repr=False)
    org_suspend_publisher: OrgSuspendPublisher | None = field(default=None, repr=False)
    enqueue_org_deletion: Callable[[str, str], None] | None = field(default=None, repr=False)


def create_app(
    *,
    settings: Settings | None = None,
    validator: TokenValidator | None = None,
    runtime: ApiRuntimeOverrides | None = None,
) -> FastAPI:
    cfg = settings or get_settings()
    hooks = runtime or ApiRuntimeOverrides()
    state = ApiAppState(
        settings=cfg,
        token_revoker=hooks.token_revoker,
        token_manager=hooks.token_manager,
        provider_credential_manager=hooks.provider_credential_manager,
        org_suspend_publisher=hooks.org_suspend_publisher,
        enqueue_org_deletion=hooks.enqueue_org_deletion,
    )

    @asynccontextmanager
    async def lifespan(application: FastAPI) -> AsyncGenerator[None, None]:
        async with _api_service_lifespan(state, cfg, validator):
            yield

    application = FastAPI(
        title="IBEX Management API",
        version="0.2.0",
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
    application.include_router(organizations_router)
    application.include_router(users_router)
    application.include_router(agents_router)
    application.include_router(tokens_router)
    application.include_router(providers_router)
    application.add_middleware(HTTPMetricsMiddleware)
    application.add_middleware(RequestIdMiddleware)
    return application


def _mark_not_ready(state: ApiAppState, message: str) -> None:
    state.ready = False
    state.ready_error = message
    logger.error("api not ready: %s request_id=%s", message, request_id_for_log())


def _wire_runtime_defaults(state: ApiAppState, cfg: Settings) -> None:
    if state.token_revoker is None:
        from authclient.revoke import GRPCTokenRevoker

        state.token_revoker = GRPCTokenRevoker(
            cfg.auth_grpc_addr,
            timeout_seconds=max(cfg.auth_timeout_ms / 1000.0, 0.2),
        )
    if state.token_manager is None:
        from authclient.tokens import GRPCTokenManager

        state.token_manager = GRPCTokenManager(
            cfg.auth_grpc_addr,
            timeout_seconds=max(cfg.auth_timeout_ms / 1000.0, 0.2),
        )
    if state.provider_credential_manager is None:
        from authclient.provider_credentials import GRPCProviderCredentialManager

        state.provider_credential_manager = GRPCProviderCredentialManager(
            cfg.auth_grpc_addr,
            timeout_seconds=max(cfg.auth_timeout_ms / 1000.0, 0.2),
        )
    if state.org_suspend_publisher is None:
        state.org_suspend_publisher = (
            RedisOrgSuspendPublisher(cfg.redis_url)
            if cfg.redis_url
            else NoopOrgSuspendPublisher()
        )
    if state.enqueue_org_deletion is None:
        from app.services.organizations import unconfigured_org_deletion_enqueue

        state.enqueue_org_deletion = (
            _make_celery_enqueue(cfg.celery_broker_url)
            if cfg.celery_broker_url
            else unconfigured_org_deletion_enqueue
        )


async def _close_runtime(state: ApiAppState, auth: TokenValidator) -> None:
    await auth.aclose()
    closer = getattr(state.token_revoker, "aclose", None)
    if closer is not None:
        await closer()
    mgr_close = getattr(state.token_manager, "aclose", None)
    if mgr_close is not None:
        await mgr_close()
    cred_close = getattr(state.provider_credential_manager, "aclose", None)
    if cred_close is not None:
        await cred_close()
    pub_close = getattr(state.org_suspend_publisher, "aclose", None)
    if pub_close is not None:
        await pub_close()
    if state.engine is not None:
        await state.engine.dispose()
        logger.info("api service stopped request_id=%s", request_id_for_log())


async def _startup_database(
    state: ApiAppState,
    cfg: Settings,
    auth: TokenValidator,
) -> None:
    if not cfg.database_url:
        _mark_not_ready(state, "IBEX_API_DATABASE_URL not set")
        return
    engine = create_engine(cfg)
    state.engine = engine
    state.session_factory = create_session_factory(engine)
    await _refresh_readiness(state, auth=auth, engine=engine)


@asynccontextmanager
async def _api_service_lifespan(
    state: ApiAppState,
    cfg: Settings,
    validator: TokenValidator | None,
) -> AsyncGenerator[None, None]:
    logger.info("api service starting port=%s request_id=%s", cfg.port, request_id_for_log())
    auth = validator or GRPCTokenValidator(
        cfg.auth_grpc_addr,
        timeout_seconds=cfg.auth_timeout_ms / 1000.0,
    )
    state.validator = auth
    _wire_runtime_defaults(state, cfg)
    try:
        await _startup_database(state, cfg, auth)
        yield
    finally:
        await _close_runtime(state, auth)


def _make_celery_enqueue(broker_url: str) -> Callable[[str, str], None]:
    from celery import Celery

    client = Celery("ibex-api", broker=broker_url)

    def _enqueue(job_id: str, org_id: str) -> None:
        client.send_task(
            "ibex.worker.org.delete_organization",
            args=[job_id, org_id],
            queue="maintenance",
        )

    return _enqueue


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
