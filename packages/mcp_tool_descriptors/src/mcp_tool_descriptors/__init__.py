"""Recorded, checkable descriptor of a published MCP tool surface (W5.5 / P0-14).

``mcp_tools.json`` beside each MCP service records, for every published tool, the
advertised description text, the advertised input and output JSON Schema, a
canonical SHA-256 of the description and of each schema, the declared version,
and the stability and deprecation state. ``--check`` (the default) fails on any
difference between the committed record and the surface a service actually
publishes; ``--update`` is the only writer.

This package is the one implementation. A service keeps a thin
``app/descriptors.py`` that builds its own FastMCP server, names its record, and
calls ``main`` here; ``Surface`` is the single seam between the two.

Hash rule: the schema is deep-copied with every string-valued ``"title"`` key
removed — Pydantic derives titles from class and function names, so a rename
moves them without changing the contract — then serialized as
``json.dumps(schema, sort_keys=True, separators=(",", ":"), ensure_ascii=False)``
and hashed with SHA-256. The description is hashed by the same function over the
exact published text, because a model reads that text as instructions. The
schemas and the description are hashed, never the response bodies.

Every tool is recorded with ``stability: "beta"``: both surfaces are provisional,
and the record says so rather than implying stable support. That claim lives in
``engineering/architecture-v2/00-status-and-evidence.md`` and is not upgraded
here.
"""

from mcp_tool_descriptors.checks import check, update
from mcp_tool_descriptors.cli import EXIT_DRIFT, EXIT_OK, EXIT_REFUSED, main
from mcp_tool_descriptors.hashing import canonical_sha256, short_digest
from mcp_tool_descriptors.paths import (
    ALLOW_ROOT_ENV,
    RefusedPath,
    confine,
    default_allow_root,
)
from mcp_tool_descriptors.record import (
    DESCRIPTOR_SCHEMA,
    GENERATOR_COMMAND,
    SCHEMA_FIELDS,
    STABILITY,
    PublishedTool,
    Surface,
    build_record,
    generator,
    row_for,
)
from mcp_tool_descriptors.writer import write_atomic

__all__ = [
    "ALLOW_ROOT_ENV",
    "DESCRIPTOR_SCHEMA",
    "EXIT_DRIFT",
    "EXIT_OK",
    "EXIT_REFUSED",
    "GENERATOR_COMMAND",
    "SCHEMA_FIELDS",
    "STABILITY",
    "PublishedTool",
    "RefusedPath",
    "Surface",
    "build_record",
    "canonical_sha256",
    "check",
    "confine",
    "default_allow_root",
    "generator",
    "main",
    "row_for",
    "short_digest",
    "update",
    "write_atomic",
]
