"""FastAPI host for MCP Streamable HTTP + health/discovery."""

from __future__ import annotations

import logging
from collections.abc import AsyncGenerator, Callable
from contextlib import AbstractAsyncContextManager, asynccontextmanager
from dataclasses import dataclass
from typing import Any

from fastapi import FastAPI

from app.audit import AsyncAuditEmitter, AuditSink, build_audit_sink
from app.auth import GRPCTokenValidator, TokenValidator
from app.auth_breaker import (
    AUTH_BREAKER_COOLDOWN_S,
    AUTH_BREAKER_FAILURES,
    BreakingTokenValidator,
)
from app.clients.memory import MemoryHttpClient, build_memory_client
from app.config import Settings, get_settings
from app.http_metrics import HTTPMetricsMiddleware
from app.middleware import BearerAuthConfig, BearerAuthMiddleware
from app.probes import probe_router
from app.ratelimit import McpRateLimiter, RedisMcpLimiter, build_mcp_rate_limiter
from app.server import build_mcp_server
from app.state import AppState

logger = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class CreateAppDeps:
    """Optional test/production injections (keeps create_app under CodeScene arity)."""

    validator: TokenValidator | None = None
    audit_sink: AuditSink | None = None
    memory_client: MemoryHttpClient | None = None
    rate_limiter: McpRateLimiter | None = None


@dataclass(slots=True)
class _Runtime:
    state: AppState
    injected: CreateAppDeps
    cfg: Settings
    audit: AsyncAuditEmitter
    mem: MemoryHttpClient | None
    owned_memory: bool
    limiter: McpRateLimiter
    owned_limiter: bool
    mcp: Any


def create_app(
    *,
    settings: Settings | None = None,
    deps: CreateAppDeps | None = None,
) -> FastAPI:
    cfg = settings or get_settings()
    injected = deps or CreateAppDeps()
    state = AppState()
    sink = injected.audit_sink or build_audit_sink(cfg.clickhouse_url)
    audit = AsyncAuditEmitter(sink, maxsize=cfg.audit_queue_size)
    mem, owned_memory = _resolve_memory_client(cfg, injected.memory_client)
    limiter, owned_limiter = _resolve_rate_limiter(cfg, injected.rate_limiter)
    mcp = build_mcp_server(
        audit,
        mem,
        rate_limiter=limiter,
        allow_test_hosts=cfg.env != "production",
    )
    runtime = _Runtime(
        state=state,
        injected=injected,
        cfg=cfg,
        audit=audit,
        mem=mem,
        owned_memory=owned_memory,
        limiter=limiter,
        owned_limiter=owned_limiter,
        mcp=mcp,
    )
    application = FastAPI(
        title="IBEX MCP Memory",
        version="0.1.0",
        lifespan=_build_lifespan(runtime),
    )
    application.state.mcp = state
    application.state.settings = cfg
    application.include_router(probe_router)
    # Mount at root: FastMCP exposes /mcp; FastAPI routes (/health, /ready) win first.
    application.mount("/", mcp.streamable_http_app())
    # Inner auth first, then metrics outermost so 401s are counted.
    application.add_middleware(
        BearerAuthMiddleware,
        config=BearerAuthConfig(
            settings=cfg,
            get_validator=lambda: state.validator or injected.validator,
            get_audit=lambda: state.audit,
        ),
    )
    application.add_middleware(HTTPMetricsMiddleware)
    return application


def _build_lifespan(
    runtime: _Runtime,
) -> Callable[[FastAPI], AbstractAsyncContextManager[None]]:
    @asynccontextmanager
    async def lifespan(_application: FastAPI) -> AsyncGenerator[None, None]:
        inner = runtime.injected.validator or GRPCTokenValidator(
            runtime.cfg.auth_grpc_addr,
            timeout_seconds=runtime.cfg.auth_timeout_ms / 1000.0,
        )
        auth = _with_auth_breaker(inner)
        runtime.state.validator = auth
        runtime.state.audit = runtime.audit
        runtime.state.memory_client = runtime.mem
        runtime.state.rate_limiter = runtime.limiter
        runtime.state.mcp_app = runtime.mcp
        runtime.audit.start()
        try:
            await _mark_readiness(runtime.state, auth, runtime.cfg)
            async with runtime.mcp.session_manager.run():
                yield
        finally:
            await _shutdown(runtime, auth)

    return lifespan


async def _shutdown(runtime: _Runtime, auth: TokenValidator) -> None:
    runtime.state.ready = False
    await runtime.audit.aclose()
    await auth.aclose()
    if runtime.owned_memory and runtime.mem is not None:
        await runtime.mem.aclose()
    if runtime.owned_limiter and isinstance(runtime.limiter, RedisMcpLimiter):
        await runtime.limiter.aclose()
    logger.info("mcp-memory shutdown complete")


def _with_auth_breaker(inner: TokenValidator) -> TokenValidator:
    if isinstance(inner, BreakingTokenValidator):
        return inner
    return BreakingTokenValidator(
        inner,
        failure_threshold=AUTH_BREAKER_FAILURES,
        cooldown_seconds=AUTH_BREAKER_COOLDOWN_S,
    )


def _resolve_memory_client(
    cfg: Settings,
    injected: MemoryHttpClient | None,
) -> tuple[MemoryHttpClient | None, bool]:
    """Return (client, owns_lifecycle). Injected clients are not closed by lifespan."""
    if injected is not None:
        return injected, False
    if not cfg.memory_http_url.strip():
        logger.warning(
            "IBEX_MEMORY_HTTP_URL unset — search_memory/write_memory/record_feedback will fail closed"
        )
        return None, False
    return (
        build_memory_client(
            base_url=cfg.memory_http_url,
            timeout_seconds=cfg.memory_timeout_ms / 1000.0,
        ),
        True,
    )


def _resolve_rate_limiter(
    cfg: Settings,
    injected: McpRateLimiter | None,
) -> tuple[McpRateLimiter, bool]:
    if injected is not None:
        return injected, False
    return (
        build_mcp_rate_limiter(
            redis_url=cfg.redis_url,
            default_rpm=cfg.rate_limit_rpm,
            org_overrides=cfg.rate_limit_org_override_map,
        ),
        True,
    )


async def _mark_readiness(state: AppState, auth: TokenValidator, cfg: Settings) -> None:
    if not await auth.ready():
        state.ready = False
        state.ready_error = "auth gRPC not reachable"
        logger.error("mcp-memory not ready: auth gRPC unreachable")
        return
    state.ready = True
    state.ready_error = None
    logger.info(
        "mcp-memory ready transport=%s auth_grpc=%s memory_http=%s redis=%s",
        cfg.transport,
        cfg.auth_grpc_addr,
        "configured" if cfg.memory_http_url.strip() else "unset",
        "configured" if cfg.redis_url.strip() else "unset",
    )


app = create_app()
