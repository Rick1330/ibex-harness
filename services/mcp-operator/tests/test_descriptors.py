"""The committed operator tool record against the surface the gateway publishes (W5.5).

The drift matrix lives in ``packages/mcp_tool_descriptors`` and runs against a
synthetic surface. This suite pins the two things only this service can: that the
committed ``mcp_tools.json`` still describes the four tools the enforcer
advertises — with the version and the canonical input schema each ``ToolSpec``
declares — and that enumeration never executes a tool.
"""

from __future__ import annotations

import asyncio
import json
from pathlib import Path
from typing import Any

import pytest
from mcp_tool_descriptors import canonical_sha256, check, update

from app import descriptors
from app.tools import build_registry

COMMITTED = Path(__file__).resolve().parents[1] / "mcp_tools.json"
GATEWAY_TOOLS = ("budget.get", "evidence.query", "run.get", "session.get")


def _rows() -> dict[str, dict[str, Any]]:
    record = json.loads(COMMITTED.read_text(encoding="utf-8"))
    return {entry["name"]: entry for entry in record["tools"]}


def _published() -> dict[str, Any]:
    return {tool.name: tool for tool, _ in asyncio.run(descriptors.published())}


def _specs() -> dict[str, Any]:
    return {spec.name: spec for spec in build_registry().specs()}


def test_committed_record_matches_the_published_surface() -> None:
    assert check(descriptors.SURFACE, COMMITTED, allow_root=COMMITTED.parent) == []


def test_record_and_surface_cover_the_same_four_gateway_tools() -> None:
    assert descriptors.DESCRIPTOR_PATH == COMMITTED
    assert tuple(sorted(_rows())) == GATEWAY_TOOLS
    assert tuple(sorted(_published())) == GATEWAY_TOOLS


def test_every_row_carries_the_version_its_tool_spec_declares() -> None:
    """The operator gateway owns a per-tool version, so provenance is testable here."""
    specs = _specs()
    rows = _rows()
    for name in GATEWAY_TOOLS:
        assert rows[name]["version"], f"{name} recorded no version"
        assert rows[name]["version"] == specs[name].version


def test_every_row_records_the_registry_canonical_input_schema() -> None:
    """Enumeration happens after ``bind_declared_schemas``, so the row is the wire schema."""
    specs = _specs()
    rows = _rows()
    for name in GATEWAY_TOOLS:
        assert rows[name]["input_schema"] == specs[name].input_schema
        assert rows[name]["input_schema"]["additionalProperties"] is False


def test_every_row_pins_the_published_description() -> None:
    published = _published()
    for name, entry in _rows().items():
        assert entry["description_sha256"] == canonical_sha256(published[name].description or "")


async def test_enumeration_refuses_to_execute_a_tool() -> None:
    with pytest.raises(RuntimeError, match="must not execute"):
        await descriptors._refuse_call(None, {})  # type: ignore[arg-type]


def test_two_regenerations_in_one_runtime_agree(tmp_path: Path) -> None:
    """Determinism is a property of the generator, so two runs here must agree byte for byte.

    The committed record is pinned by the ``--check`` test above; comparing a fresh
    record against it would make determinism fail for a contract change it does not
    own.
    """
    targets = [tmp_path / "first.json", tmp_path / "second.json"]
    for target in targets:
        assert update(descriptors.SURFACE, target, allow_root=tmp_path) == len(GATEWAY_TOOLS)
        written = json.loads(target.read_text(encoding="utf-8"))
        assert tuple(sorted(entry["name"] for entry in written["tools"])) == GATEWAY_TOOLS
    assert targets[0].read_bytes() == targets[1].read_bytes()
