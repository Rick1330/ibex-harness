"""Call FastMCP-registered tools with principal context."""

from __future__ import annotations

from uuid import UUID, uuid4

import httpx
import pytest

from app.access_token import set_access_token
from app.audit import AsyncAuditEmitter, MemoryAuditSink
from app.clients.memory import MemoryHttpClient, MemoryHttpConfig
from app.permissions import MEMORY_READ, MEMORY_WRITE
from app.principal import Principal, set_principal
from app.server import build_mcp_server

ORG = UUID("11111111-1111-1111-1111-111111111111")
AGENT = UUID("22222222-2222-2222-2222-222222222222")
TOKEN = "tok-fastmcp"


def _memory_client(handler) -> MemoryHttpClient:
    return MemoryHttpClient(
        MemoryHttpConfig(base_url="http://memory.test", timeout_seconds=1.0),
        client=httpx.AsyncClient(transport=httpx.MockTransport(handler)),
    )


@pytest.mark.asyncio
async def test_fastmcp_call_tools() -> None:
    mid = str(uuid4())

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/search"):
            return httpx.Response(200, json={"data": {"results": []}})
        return httpx.Response(
            201,
            json={
                "data": {
                    "id": mid,
                    "agent_id": str(AGENT),
                    "org_id": str(ORG),
                    "category": "factual",
                    "confidence": 0.7,
                    "source": "user_provided",
                    "status": "active",
                    "metadata": {"mcp_source": "mcp_explicit"},
                }
            },
        )

    client = _memory_client(handler)
    sink = MemoryAuditSink()
    audit = AsyncAuditEmitter(sink, maxsize=16)
    audit.start()
    mcp = build_mcp_server(audit, client)
    set_principal(Principal(org_id=ORG, permissions=MEMORY_READ | MEMORY_WRITE, agent_id=AGENT))
    set_access_token(TOKEN)
    try:
        search = await mcp.call_tool(
            "search_memory",
            {"query": "q", "limit": 3},
        )
        write = await mcp.call_tool(
            "write_memory",
            {
                "content": "c",
                "category": "factual",
                "confidence": 0.7,
            },
        )
    finally:
        set_principal(None)
        set_access_token(None)
        await audit.aclose()
        await client.aclose()
    assert search is not None
    assert write is not None


@pytest.mark.asyncio
async def test_tools_list_schemas_advertise_constraints() -> None:
    sink = MemoryAuditSink()
    audit = AsyncAuditEmitter(sink, maxsize=4)
    mcp = build_mcp_server(audit, None)
    tools = await mcp.list_tools()
    by_name = {t.name: t for t in tools}
    assert set(by_name) == {"search_memory", "write_memory"}

    search = by_name["search_memory"].inputSchema
    assert search.get("additionalProperties") is False
    query = search["properties"]["query"]
    assert query.get("minLength") == 1
    assert query.get("maxLength") == 2000
    limit = search["properties"]["limit"]
    assert limit.get("minimum") == 1
    assert limit.get("maximum") == 50
    agent = search["properties"]["agent_id"]
    assert agent.get("format") == "uuid" or "uuid" in str(agent).lower()

    write = by_name["write_memory"].inputSchema
    assert write.get("additionalProperties") is False
    content = write["properties"]["content"]
    assert content.get("minLength") == 1
    assert content.get("maxLength") == 8000
    category = write["properties"]["category"]
    assert set(category.get("enum", [])) == {
        "factual",
        "preference",
        "behavioral",
        "episodic",
        "procedural",
    }
    confidence = write["properties"]["confidence"]
    assert confidence.get("minimum") == 0.0
    assert confidence.get("maximum") == 1.0


@pytest.mark.asyncio
async def test_unknown_tool_argument_rejected_before_execution() -> None:
    sink = MemoryAuditSink()
    audit = AsyncAuditEmitter(sink, maxsize=4)
    audit.start()
    mcp = build_mcp_server(audit, None)
    set_principal(Principal(org_id=ORG, permissions=MEMORY_READ | MEMORY_WRITE, agent_id=AGENT))
    try:
        with pytest.raises(Exception, match="[Ee]xtra|limti|validation"):
            await mcp.call_tool("search_memory", {"query": "q", "limti": 3})
    finally:
        set_principal(None)
        await audit.aclose()
    assert sink.events == []
