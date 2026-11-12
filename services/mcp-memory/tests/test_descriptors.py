"""The committed memory tool record and the schema the server really advertises (W5.5).

The drift matrix lives in ``packages/mcp_tool_descriptors``. This suite pins what
is specific to the memory server: one surface version for every row, and the
post-registration rewrite — ``_forbid_undeclared_tool_args`` replaces each
advertised input schema with the ``Annotated`` arg model's, so the ``*_SCHEMA``
constants in ``app/tools.py`` are not what a client sees.
"""

from __future__ import annotations

import asyncio
import json
from pathlib import Path
from typing import Any

from mcp_tool_descriptors import canonical_sha256, main

from app import descriptors
from app.tools import (
    GET_MEMORY_LINEAGE_SCHEMA,
    RECORD_FEEDBACK_SCHEMA,
    SEARCH_MEMORY_SCHEMA,
    WRITE_MEMORY_SCHEMA,
)

COMMITTED = Path(__file__).resolve().parents[1] / "mcp_tools.json"
MEMORY_TOOLS = ("get_memory_lineage", "record_feedback", "search_memory", "write_memory")
SURFACE_VERSION = "1.0.0"
SCHEMA_CONSTANTS: dict[str, dict[str, Any]] = {
    "get_memory_lineage": GET_MEMORY_LINEAGE_SCHEMA,
    "record_feedback": RECORD_FEEDBACK_SCHEMA,
    "search_memory": SEARCH_MEMORY_SCHEMA,
    "write_memory": WRITE_MEMORY_SCHEMA,
}


def _published() -> list[tuple[Any, str]]:
    return asyncio.run(descriptors.published())


def _tools() -> dict[str, Any]:
    return {tool.name: tool for tool, _ in _published()}


def _rows() -> list[dict[str, Any]]:
    """The committed rows, in the order the record stores them (by tool name)."""
    return json.loads(COMMITTED.read_text(encoding="utf-8"))["tools"]


def test_the_committed_record_still_describes_the_memory_surface() -> None:
    assert descriptors.DESCRIPTOR_PATH == COMMITTED
    assert descriptors.TOOL_VERSION == SURFACE_VERSION
    code = main(descriptors.SURFACE, COMMITTED, ["--check", "--allow-root", str(COMMITTED.parent)])
    assert code == 0
    assert [entry["name"] for entry in _rows()] == list(MEMORY_TOOLS)


def test_one_version_covers_the_whole_surface() -> None:
    """There is no per-tool version registry here: a bump is one deliberate update."""
    assert {version for _, version in _published()} == {SURFACE_VERSION}
    assert {entry["version"] for entry in _rows()} == {SURFACE_VERSION}


def test_published_input_schemas_are_not_the_schema_constants() -> None:
    """The rewrite runs after registration, so the constants under-state the wire schema."""
    published = _tools()
    for name in MEMORY_TOOLS:
        assert published[name].inputSchema != SCHEMA_CONSTANTS[name]
        assert published[name].inputSchema["title"] == f"{name}Arguments"


def test_search_memory_publishes_agent_id_as_nullable() -> None:
    """The ``Annotated`` signature makes ``agent_id`` optional; the constant does not."""
    published = _tools()
    agent_id = published["search_memory"].inputSchema["properties"]["agent_id"]
    assert [branch.get("type") for branch in agent_id["anyOf"]] == ["string", "null"]
    assert SEARCH_MEMORY_SCHEMA["properties"]["agent_id"] == {
        "type": "string",
        "format": "uuid",
    }


def test_every_row_pins_the_published_description() -> None:
    published = _tools()
    for entry in _rows():
        description = published[entry["name"]].description or ""
        assert entry["description_sha256"] == canonical_sha256(description)


def test_two_regenerations_in_one_runtime_agree(tmp_path: Path) -> None:
    """Determinism is a property of the generator, so two runs here must agree byte for byte.

    The committed record is pinned by the ``--check`` test above; comparing a fresh
    record against it would make determinism fail for a contract change it does not
    own.
    """
    targets = [tmp_path / "first.json", tmp_path / "second.json"]
    for target in targets:
        assert (
            main(
                descriptors.SURFACE,
                target,
                ["--update", "--path", str(target), "--allow-root", str(tmp_path)],
            )
            == 0
        )
        record = json.loads(target.read_text(encoding="utf-8"))
        assert [entry["name"] for entry in record["tools"]] == list(MEMORY_TOOLS)
    assert targets[0].read_bytes() == targets[1].read_bytes()
