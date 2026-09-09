"""Stdio transport entrypoint (dev/test only — gated by settings)."""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass

from app.agent_verifier import AgentVerifier, GRPCAgentVerifier
from app.audit import AsyncAuditEmitter, LoggingAuditSink
from app.clients.memory import MemoryHttpClient, build_memory_client
from app.config import TRANSPORT_STDIO, Settings, get_settings
from app.ratelimit import McpRateLimiter, RedisMcpLimiter, build_mcp_rate_limiter
from app.server import McpServerWiring, build_mcp_server

logger = logging.getLogger(__name__)


@dataclass(slots=True)
class _StdioRuntime:
    mcp: object
    audit: AsyncAuditEmitter
    limiter: McpRateLimiter
    memory_client: MemoryHttpClient | None
    verifier: AgentVerifier


def build_stdio_runtime(settings: Settings) -> _StdioRuntime:
    """Wire stdio MCP the same way as HTTP create_app (including ValidateAgent)."""
    audit = AsyncAuditEmitter(LoggingAuditSink(), maxsize=settings.audit_queue_size)
    audit.start()
    memory_client = None
    if settings.memory_http_url.strip():
        memory_client = build_memory_client(
            base_url=settings.memory_http_url,
            timeout_seconds=settings.memory_timeout_ms / 1000.0,
        )
    limiter = build_mcp_rate_limiter(
        redis_url=settings.redis_url,
        default_rpm=settings.rate_limit_rpm,
        org_overrides=settings.rate_limit_org_override_map,
    )
    verifier: AgentVerifier = GRPCAgentVerifier(
        settings.auth_grpc_addr,
        timeout_seconds=settings.auth_timeout_ms / 1000.0,
    )
    mcp = build_mcp_server(
        McpServerWiring(
            audit=audit,
            memory_client=memory_client,
            agent_verifier=verifier,
            rate_limiter=limiter,
        )
    )
    return _StdioRuntime(
        mcp=mcp,
        audit=audit,
        limiter=limiter,
        memory_client=memory_client,
        verifier=verifier,
    )


async def aclose_stdio_runtime(runtime: _StdioRuntime) -> None:
    await runtime.audit.aclose()
    await runtime.verifier.aclose()
    if runtime.memory_client is not None:
        await runtime.memory_client.aclose()
    if isinstance(runtime.limiter, RedisMcpLimiter):
        await runtime.limiter.aclose()


def main() -> None:
    settings = get_settings()
    if settings.transport != TRANSPORT_STDIO:
        raise SystemExit("stdio_main requires IBEX_MCP_TRANSPORT=stdio")
    settings.validate_transport_policy()
    asyncio.run(_run())


async def _run() -> None:
    settings = get_settings()
    runtime = build_stdio_runtime(settings)
    try:
        await runtime.mcp.run_stdio_async()  # type: ignore[attr-defined]
    finally:
        await aclose_stdio_runtime(runtime)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    main()
