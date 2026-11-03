"""FastAPI host for the read-only MCP operator gateway (default off).

When ``IBEX_MCP_OPERATOR_ENABLED`` is false the process serves only probes and
metrics (no ``/mcp`` surface, no DB, no auth dependency). When enabled it mounts
the Streamable HTTP MCP server behind bearer auth and the enforcement pipeline.
"""

from __future__ import annotations

import logging
from collections.abc import AsyncGenerator, Callable
from contextlib import AbstractAsyncContextManager, asynccontextmanager
from dataclasses import dataclass
from typing import Any

from fastapi import FastAPI
from mcp_gateway import BitmapPolicyEvaluator, EnforcerOptions, GatewayEnforcer
from sqlalchemy.ext.asyncio import AsyncEngine

from app.audit import AsyncAuditEmitter, AuditSink, build_operator_audit_sink
from app.auth import GRPCTokenValidator, TokenValidator
from app.auth_breaker import (
    AUTH_BREAKER_COOLDOWN_S,
    AUTH_BREAKER_FAILURES,
    BreakingTokenValidator,
)
from app.config import Settings, get_settings
from app.db import create_engine, create_session_factory
from app.http_metrics import HTTPMetricsMiddleware
from app.logging import configure_logging
from app.middleware import BearerAuthConfig, BearerAuthMiddleware
from app.probes import probe_router
from app.ratelimit import OperatorRateLimiter, RedisOperatorLimiter, build_operator_rate_limiter
from app.server import McpServerWiring, build_mcp_server
from app.state import AppState
from app.tools import ToolDispatcher, build_registry
from app.tracing import TracingMiddleware, configure_tracing, shutdown_tracing

logger = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class CreateAppDeps:
    """Optional test/production injections (keeps create_app arity small)."""

    validator: TokenValidator | None = None
    rate_limiter: OperatorRateLimiter | None = None
    audit_sink: AuditSink | None = None
    executor: Any | None = None


@dataclass(slots=True)
class _Runtime:
    state: AppState
    injected: CreateAppDeps
    cfg: Settings
    audit: AsyncAuditEmitter
    engine: AsyncEngine | None
    owned_engine: bool
    limiter: OperatorRateLimiter
    owned_limiter: bool
    mcp: Any | None


def create_app(
    *,
    settings: Settings | None = None,
    deps: CreateAppDeps | None = None,
) -> FastAPI:
    cfg = settings or get_settings()
    injected = deps or CreateAppDeps()
    configure_logging()
    configure_tracing(cfg.otel_endpoint)
    state = AppState(enabled=cfg.enabled)
    audit = AsyncAuditEmitter(
        injected.audit_sink or build_operator_audit_sink(cfg.clickhouse_url),
        maxsize=cfg.audit_queue_size,
    )
    engine, owned_engine = _resolve_engine(cfg, injected)
    limiter, owned_limiter = _resolve_rate_limiter(cfg, injected.rate_limiter)
    mcp = _build_mcp_app(_McpBuildConfig(cfg, injected, limiter, audit, engine))

    runtime = _Runtime(
        state=state,
        injected=injected,
        cfg=cfg,
        audit=audit,
        engine=engine,
        owned_engine=owned_engine,
        limiter=limiter,
        owned_limiter=owned_limiter,
        mcp=mcp,
    )
    application = FastAPI(
        title="IBEX MCP Operator Gateway",
        version="0.1.0",
        lifespan=_build_lifespan(runtime),
    )
    application.state.operator = state
    application.state.settings = cfg
    application.include_router(probe_router)
    if mcp is not None:
        application.mount("/", mcp.streamable_http_app())
        application.add_middleware(
            BearerAuthMiddleware,
            config=BearerAuthConfig(
                settings=cfg,
                get_validator=lambda: state.validator or injected.validator,
                get_audit=lambda: state.audit,
            ),
        )
    application.add_middleware(HTTPMetricsMiddleware)
    application.add_middleware(TracingMiddleware)
    return application


def _resolve_engine(cfg: Settings, injected: CreateAppDeps) -> tuple[AsyncEngine | None, bool]:
    if injected.executor is not None or not cfg.enabled:
        return None, False
    engine = create_engine(cfg)
    return engine, True


@dataclass(frozen=True, slots=True)
class _McpBuildConfig:
    cfg: Settings
    injected: CreateAppDeps
    limiter: OperatorRateLimiter
    audit: AsyncAuditEmitter
    engine: AsyncEngine | None


def _build_mcp_app(deps: _McpBuildConfig) -> Any | None:
    if not deps.cfg.enabled:
        return None
    registry = build_registry()
    executor = deps.injected.executor
    if executor is None:
        if deps.engine is None:  # pragma: no cover - guarded by config validation
            raise RuntimeError("database engine is required for the operator gateway")
        executor = ToolDispatcher(create_session_factory(deps.engine))
    enforcer = GatewayEnforcer(
        registry,
        executor,
        options=EnforcerOptions(
            policy=BitmapPolicyEvaluator(),
            rate_limiter=deps.limiter,
            audit=deps.audit,
        ),
    )
    return build_mcp_server(
        McpServerWiring(
            enforcer=enforcer,
            registry=registry,
            allow_test_hosts=deps.cfg.env != "production",
            resource_url=deps.cfg.resource_url,
        )
    )


def _build_lifespan(
    runtime: _Runtime,
) -> Callable[[FastAPI], AbstractAsyncContextManager[None]]:
    @asynccontextmanager
    async def lifespan(_application: FastAPI) -> AsyncGenerator[None, None]:
        runtime.state.audit = runtime.audit
        runtime.state.rate_limiter = runtime.limiter
        runtime.state.engine = runtime.engine
        runtime.audit.start()
        if not runtime.cfg.enabled:
            runtime.state.ready = True
            logger.info("mcp-operator disabled (no /mcp surface mounted)")
            try:
                yield
            finally:
                await _shutdown(runtime, validator=None)
            return
        validator = _with_auth_breaker(
            runtime.injected.validator
            or GRPCTokenValidator(
                runtime.cfg.auth_grpc_addr,
                timeout_seconds=runtime.cfg.auth_timeout_ms / 1000.0,
            )
        )
        runtime.state.validator = validator
        runtime.state.mcp_app = runtime.mcp
        runtime.state.session_factory = (
            create_session_factory(runtime.engine) if runtime.engine is not None else None
        )
        try:
            await _mark_readiness(runtime.state, validator, runtime.cfg)
            async with runtime.mcp.session_manager.run():
                yield
        finally:
            await _shutdown(runtime, validator=validator)

    return lifespan


async def _shutdown(runtime: _Runtime, validator: TokenValidator | None) -> None:
    runtime.state.ready = False
    await runtime.audit.aclose()
    if validator is not None:
        await validator.aclose()
    if runtime.owned_limiter and isinstance(runtime.limiter, RedisOperatorLimiter):
        await runtime.limiter.aclose()
    if runtime.owned_engine and runtime.engine is not None:
        await runtime.engine.dispose()
    shutdown_tracing()
    logger.info("mcp-operator shutdown complete")


def _with_auth_breaker(inner: TokenValidator) -> TokenValidator:
    if isinstance(inner, BreakingTokenValidator):
        return inner
    return BreakingTokenValidator(
        inner,
        failure_threshold=AUTH_BREAKER_FAILURES,
        cooldown_seconds=AUTH_BREAKER_COOLDOWN_S,
    )


def _resolve_rate_limiter(
    cfg: Settings,
    injected: OperatorRateLimiter | None,
) -> tuple[OperatorRateLimiter, bool]:
    if injected is not None:
        return injected, False
    return (
        build_operator_rate_limiter(
            redis_url=cfg.redis_url,
            default_rpm=cfg.rate_limit_rpm,
            org_overrides=cfg.rate_limit_org_override_map,
            fail_closed=cfg.protected_profile,
        ),
        True,
    )


async def _mark_readiness(state: AppState, validator: TokenValidator, cfg: Settings) -> None:
    if not await validator.ready():
        state.ready = False
        state.ready_error = "auth gRPC not reachable"
        logger.error("mcp-operator not ready: auth gRPC unreachable")
        return
    state.ready = True
    state.ready_error = None
    logger.info(
        "mcp-operator ready transport=streamable_http auth_grpc=%s redis=%s clickhouse=%s",
        cfg.auth_grpc_addr,
        "configured" if cfg.redis_url.strip() else "unset",
        "configured" if cfg.clickhouse_url.strip() else "unset",
    )


app = create_app()
