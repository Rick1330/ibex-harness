"""The record a service writes: the surface contract and the committed row shape.

A *surface* is what a service publishes right now. This package is told about it
through ``Surface`` and never builds a server itself: the service keeps that
knowledge, because the MCP services construct their daemons differently (the
operator gateway builds a registry plus an enforcer, the memory server builds a
wiring with an audit sink). Everything a row contains — the advertised
description hash, the two schema hashes, the declared version, the recorded
stability and deprecation state — is decided here, so the two services cannot
record the same contract two ways.
"""

from __future__ import annotations

import asyncio
import platform
from collections.abc import Awaitable, Callable, Iterable
from dataclasses import dataclass
from importlib import metadata
from typing import Any, Final

import pydantic
from mcp import types

from mcp_tool_descriptors.hashing import canonical_sha256

DESCRIPTOR_SCHEMA: Final = "ibex.mcp-tool-descriptor.v1"
GENERATOR_COMMAND: Final = "python -m app.descriptors --update"
STABILITY: Final = "beta"
SCHEMA_FIELDS: Final = ("input", "output")

#: One published tool and the version its service declares for it. A tool with no
#: declared version pairs with ``""``, and ``refuse_undeclared_versions`` rejects
#: that during ``--update`` instead of storing a contract gap.
PublishedTool = tuple[types.Tool, str]


@dataclass(frozen=True, slots=True)
class Surface:
    """One service's published MCP surface.

    ``service`` names the FastMCP server, so ``--help`` says which surface a
    command is about. ``publish`` is awaited because ``FastMCP.list_tools`` is
    async, and it returns every advertised tool with the version that service
    declares: the operator gateway reads a per-tool version from its registry,
    while the memory server declares one version for the whole surface.
    """

    service: str
    publish: Callable[[], Awaitable[Iterable[PublishedTool]]]


def generator() -> dict[str, str]:
    """Identify what wrote the record, so a reader knows which runtime produced it."""
    return {
        "schema": DESCRIPTOR_SCHEMA,
        "command": GENERATOR_COMMAND,
        "python": platform.python_version(),
        "mcp": metadata.version("mcp"),
        "pydantic": pydantic.VERSION,
    }


def build_record(surface: Surface) -> dict[str, Any]:
    """Return the record for the surface published right now (what ``--update`` writes)."""
    published = sorted(asyncio.run(surface.publish()), key=lambda item: item[0].name)
    return {
        "generator": generator(),
        "tools": [row_for(tool, version) for tool, version in published],
    }


def row_for(tool: types.Tool, version: str) -> dict[str, Any]:
    """One committed row: schemas verbatim (a readable diff) plus their canonical hashes."""
    return {
        "name": tool.name,
        "version": version,
        "stability": STABILITY,
        "deprecated": False,
        "description_sha256": canonical_sha256(tool.description or ""),
        "input_schema_sha256": canonical_sha256(tool.inputSchema),
        "output_schema_sha256": canonical_sha256(tool.outputSchema),
        "input_schema": tool.inputSchema,
        "output_schema": tool.outputSchema,
    }


def refuse_undeclared_versions(tools: list[dict[str, Any]]) -> None:
    """A record must not store an empty version: that is a contract gap, not a row."""
    undeclared = [str(row.get("name")) for row in tools if not row.get("version")]
    if undeclared:
        raise SystemExit(f"published tool(s) with no declared version: {', '.join(undeclared)}")
