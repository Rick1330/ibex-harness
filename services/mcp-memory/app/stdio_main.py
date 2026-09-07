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
        from app.clients.memory import MemoryHttpClient, MemoryHttpConfig

        memory_client = MemoryHttpClient(
            MemoryHttpConfig(
                base_url=settings.memory_http_url,
                timeout_seconds=settings.memory_timeout_ms / 1000.0,
            )
        )
    mcp = build_mcp_server(audit, memory_client)
    try:
        await mcp.run_stdio_async()
    finally:
        await audit.aclose()
        if memory_client is not None:
            await memory_client.aclose()


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    main()
