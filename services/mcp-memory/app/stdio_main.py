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
    audit = AsyncAuditEmitter(LoggingAuditSink(), maxsize=get_settings().audit_queue_size)
    audit.start()
    mcp = build_mcp_server(audit)
    try:
        await mcp.run_stdio_async()
    finally:
        await audit.aclose()


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    main()
