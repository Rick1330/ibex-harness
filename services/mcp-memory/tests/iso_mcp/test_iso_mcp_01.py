"""ISO-MCP-01: cross-org agent_id must be permission_denied (never not_found)."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app.audit import MemoryAuditSink
from tests.iso_mcp.conftest import (
    assert_permission_denied,
    mcp_session,
    tools_call,
)

pytestmark = pytest.mark.iso_mcp


def test_iso_mcp_01_cross_org_agent_denied_on_search_and_write(
    iso_app: tuple[TestClient, MemoryAuditSink],
    iso_env: dict[str, str],
    iso_ids: dict[str, object],
) -> None:
    client, sink = iso_app
    headers = mcp_session(client, iso_env["token_a"])
    agent_b = str(iso_ids["agent_b"])

    search = tools_call(
        client,
        headers=headers,
        request_id=10,
        name="search_memory",
        arguments={"query": "cross-tenant", "agent_id": agent_b},
    )
    assert_permission_denied(search, sink=sink)

    write = tools_call(
        client,
        headers=headers,
        request_id=11,
        name="write_memory",
        arguments={"content": "must not write across orgs", "agent_id": agent_b},
    )
    assert_permission_denied(write, sink=sink)
