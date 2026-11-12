"""A synthetic published surface, so the negative matrix needs no service.

Two tools with fixed schemas and versions: enough rows for "one tool is added",
"one tool is removed", and "one row is duplicated", and nothing that needs a
database, an access token, or a running FastMCP server.
"""

from __future__ import annotations

import copy
import json
from pathlib import Path
from typing import Any

from mcp import types

from mcp_tool_descriptors import Surface, build_record

RECORD_NAME = "mcp_tools.json"
TOOL = "budget.get"
OTHER_TOOL = "session.get"
TOOL_COUNT = 2
VERSION = "1.0.0"

INPUT_SCHEMA: dict[str, Any] = {
    "additionalProperties": False,
    "properties": {"limit": {"default": 5, "type": "integer"}},
    "title": "BudgetGetArgs",
    "type": "object",
}
OUTPUT_SCHEMA: dict[str, Any] = {
    "properties": {"result": {"title": "Result", "type": "string"}},
    "required": ["result"],
    "title": "budget_getOutput",
    "type": "object",
}


class FakeSurface:
    """A surface the tests mutate: ``tools`` is what is published, ``versions`` its versions."""

    def __init__(self) -> None:
        self.tools = [tool(TOOL, "Get the budget."), tool(OTHER_TOOL, "Read one session.")]
        self.versions = {TOOL: VERSION, OTHER_TOOL: VERSION}

    async def publish(self) -> list[tuple[types.Tool, str]]:
        return [(item, self.versions.get(item.name, "")) for item in self.tools]

    def surface(self) -> Surface:
        return Surface(service="ibex-test", publish=self.publish)


def tool(name: str, description: str) -> types.Tool:
    return types.Tool(
        name=name,
        description=description,
        inputSchema=copy.deepcopy(INPUT_SCHEMA),
        outputSchema=copy.deepcopy(OUTPUT_SCHEMA),
    )


def record(surface: FakeSurface) -> dict[str, Any]:
    """A fresh copy of the record the current surface produces."""
    return copy.deepcopy(build_record(surface.surface()))


def row(record: dict[str, Any], name: str = TOOL) -> dict[str, Any]:
    return next(entry for entry in record["tools"] if entry["name"] == name)


def save(directory: Path, record: dict[str, Any]) -> Path:
    path = directory / RECORD_NAME
    path.write_text(
        json.dumps(record, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return path


def ghost_row(record: dict[str, Any]) -> None:
    """Record a tool the surface no longer publishes."""
    ghost = copy.deepcopy(row(record))
    ghost["name"] = "ghost.tool"
    record["tools"].append(ghost)
