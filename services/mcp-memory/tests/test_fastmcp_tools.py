"""Call FastMCP-registered tools with principal context."""

from __future__ import annotations

from uuid import UUID

import pytest

from app.access_token import set_access_token
from app.agent_verifier import AllowAllAgentVerifier
from app.audit import AsyncAuditEmitter, MemoryAuditSink
from app.permissions import MEMORY_READ, MEMORY_WRITE
from app.principal import Principal, set_principal
from app.server import build_mcp_server
from tests.memory_fixtures import stub_memory_client

ORG = UUID("11111111-1111-1111-1111-111111111111")
AGENT = UUID("22222222-2222-2222-2222-222222222222")
TOKEN = "tok-fastmcp"


@pytest.mark.asyncio
async def test_fastmcp_call_tools() -> None:
    client = stub_memory_client(org_id=ORG, agent_id=AGENT)
    sink = MemoryAuditSink()
    audit = AsyncAuditEmitter(sink, maxsize=16)
    audit.start()
    mcp = build_mcp_server(audit, client, agent_verifier=AllowAllAgentVerifier())
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
        feedback = await mcp.call_tool(
            "record_feedback",
            {
                "memory_id": str(AGENT),
                "feedback": "positive",
            },
        )
    finally:
        set_principal(None)
        set_access_token(None)
        await audit.aclose()
        await client.aclose()
    assert search is not None
    assert write is not None
    assert feedback is not None


@pytest.mark.asyncio
async def test_tools_list_schemas_advertise_constraints() -> None:
    sink = MemoryAuditSink()
    audit = AsyncAuditEmitter(sink, maxsize=4)
    mcp = build_mcp_server(audit, None, agent_verifier=AllowAllAgentVerifier())
    tools = await mcp.list_tools()
    by_name = {t.name: t for t in tools}
    assert set(by_name) == {"search_memory", "write_memory", "record_feedback"}

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



    feedback = by_name["record_feedback"].inputSchema
    assert feedback.get("additionalProperties") is False
    assert set(feedback["properties"]["feedback"].get("enum", [])) == {
        "positive",
        "negative",
        "neutral",
    }
    assert "memory_id" in feedback["properties"]
    notes = feedback["properties"]["notes"]
    # Optional[str] may nest maxLength under anyOf
    note_max = notes.get("maxLength")
    if note_max is None:
        for opt in notes.get("anyOf", []):
            if isinstance(opt, dict) and opt.get("type") == "string":
                note_max = opt.get("maxLength")
                break
    assert note_max == 2000


@pytest.mark.asyncio
async def test_unknown_tool_argument_rejected_before_execution() -> None:
    sink = MemoryAuditSink()
    audit = AsyncAuditEmitter(sink, maxsize=4)
    audit.start()
    mcp = build_mcp_server(audit, None, agent_verifier=AllowAllAgentVerifier())
    set_principal(Principal(org_id=ORG, permissions=MEMORY_READ | MEMORY_WRITE, agent_id=AGENT))
    try:
        with pytest.raises(Exception, match="[Ee]xtra|limti|validation"):
            await mcp.call_tool("search_memory", {"query": "q", "limti": 3})
    finally:
        set_principal(None)
        await audit.aclose()
    assert sink.events == []
