"""Direct tool invocation + principal coverage."""

from __future__ import annotations

import json
from uuid import UUID, uuid4

import httpx
import pytest

from app.access_token import set_access_token
from app.audit import AsyncAuditEmitter, MemoryAuditSink
from app.clients.memory import MemoryHttpClient, MemoryHttpConfig
from app.errors import PermissionDeniedError
from app.permissions import MEMORY_READ, MEMORY_WRITE
from app.principal import Principal, require_principal, set_principal
from app.server import _invoke_tool, _run_search, _run_write

ORG = UUID("11111111-1111-1111-1111-111111111111")
AGENT = UUID("22222222-2222-2222-2222-222222222222")
TOKEN = "tok-audit"


def _memory_client(handler) -> MemoryHttpClient:
    return MemoryHttpClient(
        MemoryHttpConfig(base_url="http://memory.test", timeout_seconds=1.0),
        client=httpx.AsyncClient(transport=httpx.MockTransport(handler)),
    )


def test_require_principal_missing() -> None:
    set_principal(None)
    with pytest.raises(RuntimeError):
        require_principal()


@pytest.mark.asyncio
async def test_invoke_search_and_write_emits_audit() -> None:
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
                    "confidence": 0.6,
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
    set_principal(Principal(org_id=ORG, permissions=MEMORY_READ | MEMORY_WRITE, agent_id=AGENT))
    set_access_token(TOKEN)
    try:
        search = await _invoke_tool(
            audit=audit,
            tool_name="search_memory",
            raw={"query": "hello"},
            runner=lambda raw: _run_search(raw, client),
        )
        write = await _invoke_tool(
            audit=audit,
            tool_name="write_memory",
            raw={"content": "note"},
            runner=lambda raw: _run_write(raw, client),
        )
    finally:
        set_principal(None)
        set_access_token(None)
        await audit.aclose()
        await client.aclose()

    assert json.loads(search)["results"] == []
    assert json.loads(write)["mcp_source"] == "mcp_explicit"
    assert json.loads(write)["persisted"] is True
    assert {e.tool_name for e in sink.events} == {"search_memory", "write_memory"}
    assert all(e.success for e in sink.events)


@pytest.mark.asyncio
async def test_invoke_permission_denied_audited() -> None:
    sink = MemoryAuditSink()
    audit = AsyncAuditEmitter(sink, maxsize=8)
    audit.start()
    set_principal(Principal(org_id=ORG, permissions=MEMORY_READ, agent_id=AGENT))
    set_access_token(TOKEN)
    try:
        with pytest.raises(PermissionDeniedError):
            await _invoke_tool(
                audit=audit,
                tool_name="write_memory",
                raw={"content": "x"},
                runner=lambda raw: _run_write(raw, None),
            )
    finally:
        set_principal(None)
        set_access_token(None)
        await audit.aclose()
    assert len(sink.events) == 1
    assert sink.events[0].success is False
    assert sink.events[0].error_code == "permission_denied"
