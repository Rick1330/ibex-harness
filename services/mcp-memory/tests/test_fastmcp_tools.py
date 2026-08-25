"""Call FastMCP-registered tools with principal context."""

from __future__ import annotations

from uuid import UUID

import pytest

from app.audit import AsyncAuditEmitter, MemoryAuditSink
from app.permissions import MEMORY_READ, MEMORY_WRITE
from app.principal import Principal, set_principal
from app.server import build_mcp_server

ORG = UUID("11111111-1111-1111-1111-111111111111")


@pytest.mark.asyncio
async def test_fastmcp_call_tools() -> None:
    sink = MemoryAuditSink()
    audit = AsyncAuditEmitter(sink, maxsize=16)
    audit.start()
    mcp = build_mcp_server(audit)
    set_principal(Principal(org_id=ORG, permissions=MEMORY_READ | MEMORY_WRITE))
    try:
        search = await mcp.call_tool(
            "search_memory",
            {"query": "q", "limit": 3, "agent_id": str(ORG)},
        )
        write = await mcp.call_tool(
            "write_memory",
            {
                "content": "c",
                "category": "fact",
                "confidence": 0.7,
                "agent_id": str(ORG),
            },
        )
    finally:
        set_principal(None)
        await audit.aclose()
    assert search is not None
    assert write is not None
