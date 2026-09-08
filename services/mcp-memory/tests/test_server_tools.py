"""Direct tool invocation + principal coverage."""

from __future__ import annotations

import json

import pytest

from app.access_token import set_access_token
from app.agent_verifier import AllowAllAgentVerifier
from app.audit import AsyncAuditEmitter, MemoryAuditSink
from app.errors import PermissionDeniedError
from app.permissions import MEMORY_READ, MEMORY_WRITE
from app.principal import Principal, require_principal, set_principal
from app.ratelimit import NoopMcpLimiter
from app.server import _invoke_tool, _run_search, _run_write, _ToolCall, _ToolRequest
from tests.memory_fixtures import AGENT, ORG, stub_memory_client

TOKEN = "tok-audit"
_ALLOW = AllowAllAgentVerifier()


def test_require_principal_missing() -> None:
    set_principal(None)
    with pytest.raises(RuntimeError):
        require_principal()


@pytest.mark.asyncio
async def test_invoke_search_and_write_emits_audit() -> None:
    client = stub_memory_client(org_id=ORG, agent_id=AGENT)
    sink = MemoryAuditSink()
    audit = AsyncAuditEmitter(sink, maxsize=16)
    audit.start()
    set_principal(Principal(org_id=ORG, permissions=MEMORY_READ | MEMORY_WRITE, agent_id=AGENT))
    set_access_token(TOKEN)
    try:
        search = await _invoke_tool(
            _ToolCall(
                audit=audit,
                rate_limiter=NoopMcpLimiter(),
                request=_ToolRequest(
                    tool_name="search_memory",
                    raw={"query": "hello"},
                    runner=lambda raw: _run_search(raw, client, _ALLOW),
                ),
            )
        )
        write = await _invoke_tool(
            _ToolCall(
                audit=audit,
                rate_limiter=NoopMcpLimiter(),
                request=_ToolRequest(
                    tool_name="write_memory",
                    raw={"content": "note"},
                    runner=lambda raw: _run_write(raw, client, _ALLOW),
                ),
            )
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
    call = _ToolCall(
        audit=audit,
        rate_limiter=NoopMcpLimiter(),
        request=_ToolRequest(
            tool_name="write_memory",
            raw={"content": "x"},
            runner=lambda raw: _run_write(raw, None, _ALLOW),
        ),
    )
    try:
        with pytest.raises(PermissionDeniedError):
            await _invoke_tool(call)
    finally:
        set_principal(None)
        set_access_token(None)
        await audit.aclose()
    assert len(sink.events) == 1
    assert sink.events[0].success is False
    assert sink.events[0].error_code == "permission_denied"
