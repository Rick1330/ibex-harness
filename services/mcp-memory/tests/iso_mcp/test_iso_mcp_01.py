"""ISO-MCP-01: org-scoped PAT + cross-org agent_id → ValidateAgent permission_denied.

Uses an org-scoped token (principal.agent_id is None) so resolve_tool_agent_id
forwards the foreign agent_id into ValidateAgent — not the agent-binding short
circuit that agent-scoped PATs hit first.
"""

from __future__ import annotations

import pytest

from tests.iso_mcp.conftest import (
    IsoAppCounted,
    ToolCallSpec,
    assert_no_memory_outbound,
    assert_permission_denied,
    mcp_session,
    tools_call,
)

pytestmark = pytest.mark.iso_mcp


def test_iso_mcp_01_org_scoped_cross_org_agent_denied_via_validate_agent(
    iso_app_counted: IsoAppCounted,
    iso_env: dict[str, str],
    iso_ids: dict[str, object],
) -> None:
    client = iso_app_counted.client
    sink = iso_app_counted.sink
    outbound = iso_app_counted.memory_outbound
    # Org-scoped Org A PAT (agent_id NULL) — same fixture as ISO-MCP-02.
    headers = mcp_session(client, iso_env["token_org"])
    agent_b = str(iso_ids["agent_b"])

    before = len(sink.events)
    outbound.count = 0
    search = tools_call(
        client,
        ToolCallSpec(
            headers=headers,
            request_id=10,
            name="search_memory",
            arguments={"query": "cross-tenant", "agent_id": agent_b},
        ),
    )
    assert_permission_denied(
        search, sink=sink, tool_name="search_memory", events_before=before
    )
    assert_no_memory_outbound(outbound)

    before = len(sink.events)
    outbound.count = 0
    write = tools_call(
        client,
        ToolCallSpec(
            headers=headers,
            request_id=11,
            name="write_memory",
            arguments={"content": "must not write across orgs", "agent_id": agent_b},
        ),
    )
    assert_permission_denied(
        write, sink=sink, tool_name="write_memory", events_before=before
    )
    assert_no_memory_outbound(outbound)
