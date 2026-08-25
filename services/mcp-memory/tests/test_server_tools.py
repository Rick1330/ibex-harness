"""Direct tool invocation + principal coverage."""

from __future__ import annotations

import json
from uuid import UUID

import pytest

from app.audit import AsyncAuditEmitter, MemoryAuditSink
from app.errors import PermissionDeniedError
from app.permissions import MEMORY_READ, MEMORY_WRITE
from app.principal import Principal, require_principal, set_principal
from app.server import _invoke_tool, _run_search, _run_write

ORG = UUID("11111111-1111-1111-1111-111111111111")


def test_require_principal_missing() -> None:
    set_principal(None)
    with pytest.raises(RuntimeError):
        require_principal()


@pytest.mark.asyncio
async def test_invoke_search_and_write_emits_audit() -> None:
    sink = MemoryAuditSink()
    audit = AsyncAuditEmitter(sink, maxsize=16)
    audit.start()
    set_principal(Principal(org_id=ORG, permissions=MEMORY_READ | MEMORY_WRITE))
    try:
        search = await _invoke_tool(
            audit=audit,
            tool_name="search_memory",
            raw={"query": "hello"},
            runner=_run_search,
        )
        write = await _invoke_tool(
            audit=audit,
            tool_name="write_memory",
            raw={"content": "note"},
            runner=_run_write,
        )
    finally:
        set_principal(None)
        await audit.aclose()

    assert json.loads(search)["stub"] is True
    assert json.loads(write)["source"] == "mcp_explicit"
    assert {e.tool_name for e in sink.events} == {"search_memory", "write_memory"}
    assert all(e.success for e in sink.events)


@pytest.mark.asyncio
async def test_invoke_permission_denied_audited() -> None:
    sink = MemoryAuditSink()
    audit = AsyncAuditEmitter(sink, maxsize=8)
    audit.start()
    set_principal(Principal(org_id=ORG, permissions=MEMORY_READ))
    try:
        with pytest.raises(PermissionDeniedError):
            await _invoke_tool(
                audit=audit,
                tool_name="write_memory",
                raw={"content": "x"},
                runner=_run_write,
            )
    finally:
        set_principal(None)
        await audit.aclose()
    assert len(sink.events) == 1
    assert sink.events[0].success is False
    assert sink.events[0].error_code == "permission_denied"
