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


@pytest.mark.asyncio
async def test_tools_list_schemas_advertise_constraints() -> None:
    sink = MemoryAuditSink()
    audit = AsyncAuditEmitter(sink, maxsize=4)
    mcp = build_mcp_server(audit)
    tools = await mcp.list_tools()
    by_name = {t.name: t for t in tools}
    assert set(by_name) == {"search_memory", "write_memory"}

    search = by_name["search_memory"].inputSchema
    query = search["properties"]["query"]
    assert query.get("minLength") == 1
    assert query.get("maxLength") == 2000
    limit = search["properties"]["limit"]
    assert limit.get("minimum") == 1
    assert limit.get("maximum") == 50
    agent = search["properties"]["agent_id"]
    assert agent.get("format") == "uuid" or "uuid" in str(agent).lower()

    write = by_name["write_memory"].inputSchema
    content = write["properties"]["content"]
    assert content.get("minLength") == 1
    assert content.get("maxLength") == 8000
    category = write["properties"]["category"]
    assert set(category.get("enum", [])) == {
        "fact",
        "preference",
        "procedure",
        "context",
        "other",
    }
    confidence = write["properties"]["confidence"]
    assert confidence.get("minimum") == 0.0
    assert confidence.get("maximum") == 1.0
