"""Stdio transport entrypoint (dev/test only — gated by settings)."""

from __future__ import annotations

import asyncio
import logging

from app.audit import AsyncAuditEmitter, LoggingAuditSink
from app.config import TRANSPORT_STDIO, get_settings
from app.server import build_mcp_server

logger = logging.getLogger(__name__)


def main() -> None:
    settings = get_settings()
    if settings.transport != TRANSPORT_STDIO:
        raise SystemExit("stdio_main requires IBEX_MCP_TRANSPORT=stdio")
    settings.validate_transport_policy()
    asyncio.run(_run())


async def _run() -> None:
    settings = get_settings()
    audit = AsyncAuditEmitter(LoggingAuditSink(), maxsize=settings.audit_queue_size)
    audit.start()
    memory_client = None
    if settings.memory_http_url.strip():
        from app.clients.memory import build_memory_client

        memory_client = build_memory_client(
            base_url=settings.memory_http_url,
            timeout_seconds=settings.memory_timeout_ms / 1000.0,
        )
    from app.ratelimit import build_mcp_rate_limiter

    limiter = build_mcp_rate_limiter(
        redis_url=settings.redis_url,
        default_rpm=settings.rate_limit_rpm,
        org_overrides=settings.rate_limit_org_override_map,
    )
    mcp = build_mcp_server(audit, memory_client, rate_limiter=limiter)
    try:
        await mcp.run_stdio_async()
    finally:
        await audit.aclose()
        await limiter.aclose()
        if memory_client is not None:
            await memory_client.aclose()


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    main()
