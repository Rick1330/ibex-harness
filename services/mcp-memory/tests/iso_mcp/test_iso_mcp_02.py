"""ISO-MCP-02: same-org agent owned by another user is allowed with MEMORY_*."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app.audit import MemoryAuditSink
from tests.iso_mcp.conftest import assert_tool_ok, mcp_session, tools_call

pytestmark = pytest.mark.iso_mcp


def test_iso_mcp_02_same_org_agent_created_by_other_user_allowed(
    iso_app: tuple[TestClient, MemoryAuditSink],
    iso_env: dict[str, str],
    iso_ids: dict[str, object],
) -> None:
    client, _sink = iso_app
    headers = mcp_session(client, iso_env["token_org"])
    agent_id = str(iso_ids["agent_user_b"])

    search = tools_call(
        client,
        headers=headers,
        request_id=20,
        name="search_memory",
        arguments={"query": "same-org-peer-agent", "agent_id": agent_id},
    )
    assert_tool_ok(search)

    write = tools_call(
        client,
        headers=headers,
        request_id=21,
        name="write_memory",
        arguments={
            "content": "iso-mcp-02 peer-agent write",
            "agent_id": agent_id,
            "category": "episodic",
        },
    )
    assert_tool_ok(write)
