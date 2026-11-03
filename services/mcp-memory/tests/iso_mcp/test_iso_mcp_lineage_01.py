"""ISO-MCP-LINEAGE-01: a foreign UUID answers "not found" and leaks no graph data.

What this proves at the MCP boundary: an id that belongs to another tenant is
answered with a fail-closed ``not_found`` error rather than a 200 with an empty
edge list, and no edge, status, or tip reaches the caller.

What it does **not** prove unless ``IBEX_ISO_MCP_ORG_B_MEMORY_ID`` is set: that
the root lookup filters by ``org_id``. Without that variable the probe is an
``agents.id`` from Org B, and ids are not shared between ``agents`` and
``memories``, so a traversal missing its org predicate would still return nothing
for it. The org-predicate proof lives where a real second-tenant memory can be
seeded: ``services/memory/tests/integration/test_lineage_traversal.py::
test_cross_tenant_edges_are_never_traversed``.
"""

from __future__ import annotations

import json
import os
from typing import Any

import pytest

from tests.iso_mcp.conftest import (
    IsoAppCounted,
    ToolCallSpec,
    assert_tool_ok,
    mcp_session,
    tools_call,
)

pytestmark = pytest.mark.iso_mcp


def _tool_payload(response: object) -> dict[str, Any]:
    """Decode the JSON string a handler returns through the MCP text content."""
    body = response.json()  # type: ignore[attr-defined]
    content = body["result"]["content"]
    text = content[0]["text"]
    return json.loads(text)


def _call_lineage(
    *,
    client: IsoAppCounted,
    headers: dict[str, str],
    memory_id: str,
    request_id: int,
) -> object:
    return tools_call(
        client.client,
        ToolCallSpec(
            headers=headers,
            request_id=request_id,
            name="get_memory_lineage",
            arguments={"memory_id": memory_id, "max_depth": 3},
        ),
    )


def test_iso_mcp_lineage_01_cross_org_id_is_not_found(
    iso_app_counted: IsoAppCounted,
    iso_env: dict[str, str],
    iso_ids: dict[str, object],
) -> None:
    client = iso_app_counted.client
    sink = iso_app_counted.sink
    headers = mcp_session(client, iso_env["token_org"])
    events_before = len(sink.events)

    # Prefer a real Org B memory when the environment provisions one; the
    # agent id is the fallback probe and cannot prove the org predicate.
    memory_id = (
        os.environ.get("IBEX_ISO_MCP_ORG_B_MEMORY_ID", "").strip()
        or str(iso_ids["agent_b"])
    )
    response = _call_lineage(
        client=iso_app_counted,
        headers=headers,
        memory_id=memory_id,
        request_id=42,
    )

    assert response.status_code in (200, 202), response.text
    body = response.json()
    result = body.get("result")
    assert isinstance(result, dict), body
    assert result.get("isError") is True, body
    assert "not_found" in response.text.lower(), response.text
    # No graph data may come back on the deny path.
    assert "supersession_tip" not in response.text
    new_events = sink.events[events_before:]
    assert any(
        event.tool_name == "get_memory_lineage"
        and event.success is False
        and event.error_code == "not_found"
        for event in new_events
    ), new_events


def test_iso_mcp_lineage_01_own_memory_is_traversable(
    iso_app_counted: IsoAppCounted,
    iso_env: dict[str, str],
) -> None:
    """Control case: a memory in the caller's own tenant still succeeds.

    Uses the agent-scoped Org A token: ``write_memory`` needs an agent, and taking
    it from the principal also exercises the agent-scoped ``get_memory_lineage``
    path, which resolves the agent from the token rather than from an argument.
    """
    client = iso_app_counted.client
    headers = mcp_session(client, iso_env["token_a"])

    written = tools_call(
        client,
        ToolCallSpec(
            headers=headers,
            request_id=43,
            name="write_memory",
            arguments={"content": "ISO-MCP-LINEAGE-01 control memory"},
        ),
    )
    assert_tool_ok(written)
    memory_id = str(_tool_payload(written)["memory_id"])

    response = _call_lineage(
        client=iso_app_counted,
        headers=headers,
        memory_id=memory_id,
        request_id=44,
    )
    assert_tool_ok(response)
    payload = _tool_payload(response)
    assert payload["memory_id"] == memory_id
    assert payload["supersession_tip"] == memory_id
