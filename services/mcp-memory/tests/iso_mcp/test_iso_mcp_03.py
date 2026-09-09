"""ISO-MCP-03: suspended agent PAT must get permission_denied on tools."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app.audit import MemoryAuditSink
from tests.iso_mcp.conftest import (
    ToolCallSpec,
    assert_permission_denied,
    mcp_session,
    tools_call,
)

pytestmark = pytest.mark.iso_mcp


def test_iso_mcp_03_suspended_agent_denied_on_search_and_write(
    iso_app: tuple[TestClient, MemoryAuditSink],
    iso_env: dict[str, str],
) -> None:
    client, sink = iso_app
    headers = mcp_session(client, iso_env["token_suspended"])

    before = len(sink.events)
    search = tools_call(
        client,
        ToolCallSpec(
            headers=headers,
            request_id=30,
            name="search_memory",
            arguments={"query": "suspended-agent"},
        ),
    )
    assert_permission_denied(
        search, sink=sink, tool_name="search_memory", events_before=before
    )

    before = len(sink.events)
    write = tools_call(
        client,
        ToolCallSpec(
            headers=headers,
            request_id=31,
            name="write_memory",
            arguments={"content": "must not write for suspended agent"},
        ),
    )
    assert_permission_denied(
        write, sink=sink, tool_name="write_memory", events_before=before
    )
