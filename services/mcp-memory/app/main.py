"""FastAPI host for MCP Streamable HTTP + health/discovery."""

from __future__ import annotations

import logging
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from dataclasses import dataclass

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
    # Lazily creates session_manager; must happen before lifespan uses it.
    mcp_asgi = mcp.streamable_http_app()

    @asynccontextmanager
    async def lifespan(_application: FastAPI) -> AsyncGenerator[None, None]:
        inner = injected.validator or GRPCTokenValidator(
            cfg.auth_grpc_addr,
            timeout_seconds=cfg.auth_timeout_ms / 1000.0,
        )
        auth = _with_auth_breaker(inner)
        state.validator = auth
        state.audit = audit
        state.memory_client = mem
        state.rate_limiter = limiter
        state.mcp_app = mcp
        audit.start()
        try:
            await _mark_readiness(state, auth, cfg)
            async with mcp.session_manager.run():
                yield
        finally:
            state.ready = False
            await audit.aclose()
            await auth.aclose()
            if owned_memory and mem is not None:
                await mem.aclose()
            if owned_limiter and isinstance(limiter, RedisMcpLimiter):
                await limiter.aclose()
            logger.info("mcp-memory shutdown complete")

    application = FastAPI(
        title="IBEX MCP Memory",
        version="0.1.0",
        lifespan=lifespan,
    )
    application.state.mcp = state
    application.state.settings = cfg
    application.include_router(probe_router)
    # Mount at root: FastMCP exposes /mcp; FastAPI routes (/health, /ready) win first.
    application.mount("/", mcp_asgi)
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
