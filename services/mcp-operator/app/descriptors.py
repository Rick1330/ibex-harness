"""The published MCP operator tool surface, recorded and checked (W5.5 / P0-14).

``mcp_tools.json`` beside this service records what ``/mcp`` advertises today —
``budget.get``, ``evidence.query``, ``run.get``, ``session.get`` — one row each,
with the description and both JSON Schemas hashed and the declared version taken
from the ``ToolSpec`` that owns it. The record format, every drift rule, and the
``--check``/``--update`` CLI live in ``packages/mcp_tool_descriptors``.

Enumeration builds the daemon the way ``tests/test_server.py`` does — registry,
enforcer with an audit emitter, ``build_mcp_server`` — then awaits
``mcp.list_tools()``. Nothing is read from the network or a database and no tool
is executed: the enforcer is wired to a stub that refuses calls. Enumerating
after construction matters because ``bind_declared_schemas`` replaces each
advertised input schema with the registry's canonical descriptor.
"""

from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path
from typing import Any, Final

from mcp.server.fastmcp import FastMCP
from mcp_gateway import (
    BitmapPolicyEvaluator,
    EnforcerOptions,
    GatewayEnforcer,
    InMemoryAuditEmitter,
    ToolContext,
)
from mcp_tool_descriptors import PublishedTool, Surface, main

from app.server import McpServerWiring, build_mcp_server
from app.tools import build_registry

SERVICE: Final = "ibex-mcp-operator"
DESCRIPTOR_PATH: Final = Path(__file__).resolve().parents[1] / "mcp_tools.json"


async def _refuse_call(ctx: ToolContext, args: Mapping[str, Any]) -> Mapping[str, Any]:
    raise RuntimeError("descriptor enumeration must not execute a tool")


def _server() -> FastMCP:
    """Build the daemon the way the server tests do, with a stub that refuses every call."""
    registry = build_registry()
    enforcer = GatewayEnforcer(
        registry,
        _refuse_call,
        options=EnforcerOptions(policy=BitmapPolicyEvaluator(), audit=InMemoryAuditEmitter()),
    )
    # pylint: disable=no-value-for-parameter,unexpected-keyword-arg
    # False positive: both MCP services define a top-level `app.server` module, and a
    # repo-root analysis resolves this import to the other service's wiring class
    # (which takes `audit` and has no `enforcer`). This service's class takes
    # exactly `enforcer` and `registry`; the call is correct and the tests exercise it.
    return build_mcp_server(McpServerWiring(enforcer=enforcer, registry=registry))


async def published() -> list[PublishedTool]:
    """Every advertised tool, paired with the version its ``ToolSpec`` declares."""
    versions = {spec.name: spec.version for spec in build_registry().specs()}
    tools = await _server().list_tools()
    return [(tool, versions.get(tool.name, "")) for tool in tools]


SURFACE: Final = Surface(service=SERVICE, publish=published)

if __name__ == "__main__":
    raise SystemExit(main(SURFACE, DESCRIPTOR_PATH))
