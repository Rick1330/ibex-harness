"""FastAPI host for MCP Streamable HTTP + health/discovery."""

from __future__ import annotations

import logging
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.audit import AsyncAuditEmitter, AuditSink, build_audit_sink
from app.auth import GRPCTokenValidator, TokenValidator
from app.config import Settings, get_settings
from app.http_metrics import HTTPMetricsMiddleware
from app.middleware import BearerAuthMiddleware
from app.probes import probe_router
from app.server import build_mcp_server
from app.state import AppState

logger = logging.getLogger(__name__)


def create_app(
    *,
    settings: Settings | None = None,
    validator: TokenValidator | None = None,
    audit_sink: AuditSink | None = None,
) -> FastAPI:
    cfg = settings or get_settings()
    state = AppState()
    sink = audit_sink or build_audit_sink(cfg.clickhouse_url)
    audit = AsyncAuditEmitter(sink, maxsize=cfg.audit_queue_size)
    mcp = build_mcp_server(audit, allow_test_hosts=cfg.env != "production")
    # Lazily creates session_manager; must happen before lifespan uses it.
    mcp_asgi = mcp.streamable_http_app()

    @asynccontextmanager
    async def lifespan(_application: FastAPI) -> AsyncGenerator[None, None]:
        auth = validator or GRPCTokenValidator(
            cfg.auth_grpc_addr,
            timeout_seconds=cfg.auth_timeout_ms / 1000.0,
        )
        state.validator = auth
        state.audit = audit
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
        settings=cfg,
        get_validator=lambda: state.validator or validator,
    )
    application.add_middleware(HTTPMetricsMiddleware)
    return application


async def _mark_readiness(state: AppState, auth: TokenValidator, cfg: Settings) -> None:
    if not await auth.ready():
        state.ready = False
        state.ready_error = "auth gRPC not reachable"
        logger.error("mcp-memory not ready: auth gRPC unreachable")
        return
    state.ready = True
    state.ready_error = None
    logger.info(
        "mcp-memory ready transport=%s auth_grpc=%s",
        cfg.transport,
        cfg.auth_grpc_addr,
    )


app = create_app()
