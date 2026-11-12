"""The published MCP memory tool surface, recorded and checked (W5.5 / P0-14).

``mcp_tools.json`` beside this service records what ``/mcp`` advertises today —
``get_memory_lineage``, ``record_feedback``, ``search_memory``,
``write_memory`` — one row each, with the description and both JSON Schemas
hashed. The record format, every drift rule, and the ``--check``/``--update`` CLI
live in ``packages/mcp_tool_descriptors``; this module keeps only what is
specific to the memory server.

Enumeration builds the daemon the way ``tests/test_fastmcp_tools.py`` does —
``build_mcp_server`` over an in-memory audit sink, no memory client, and an
allow-all agent verifier — and then awaits ``mcp.list_tools()``. Nothing is read
from the network, an access token, or the memory service, and no tool is ever
executed. Enumerating after construction matters because
``_forbid_undeclared_tool_args`` rewrites every advertised input schema from the
``Annotated`` signatures in ``app/server.py`` after registration, so the
``*_SCHEMA`` constants in ``app/tools.py`` are not the published surface.

One version covers the whole surface: unlike the operator gateway there is no
per-tool version registry here, so a bump is a deliberate ``--update``.
"""

from __future__ import annotations

from pathlib import Path
from typing import Final

from mcp.server.fastmcp import FastMCP
from mcp_tool_descriptors import PublishedTool, Surface, main

from app.agent_verifier import AllowAllAgentVerifier
from app.audit import AsyncAuditEmitter, MemoryAuditSink
from app.server import McpServerWiring, build_mcp_server

SERVICE: Final = "ibex-mcp-memory"
DESCRIPTOR_PATH: Final = Path(__file__).resolve().parents[1] / "mcp_tools.json"
TOOL_VERSION: Final = "1.0.0"


def _server() -> FastMCP:
    """Build the daemon the way the server tests do: in-memory audit, no memory client."""
    return build_mcp_server(
        McpServerWiring(
            audit=AsyncAuditEmitter(MemoryAuditSink(), maxsize=4),
            memory_client=None,
            agent_verifier=AllowAllAgentVerifier(),
        )
    )


async def published() -> list[PublishedTool]:
    """Every advertised tool, all on the single surface version."""
    tools = await _server().list_tools()
    return [(tool, TOOL_VERSION) for tool in tools]


SURFACE: Final = Surface(service=SERVICE, publish=published)

if __name__ == "__main__":
    raise SystemExit(main(SURFACE, DESCRIPTOR_PATH))
