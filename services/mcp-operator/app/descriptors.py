"""Recorded, checkable descriptor of the published MCP tool surface (W5.5 / P0-14).

``mcp_tools.json`` beside this service records, for every published tool, the
advertised description text, the advertised input and output JSON Schema, a
canonical SHA-256 of the description and of each schema, the declared version,
and the stability and deprecation state. ``--check`` (the default) fails on any
difference between the committed record and the surface this service actually
publishes; ``--update`` is the only writer.

Enumeration builds the daemon the way ``tests/test_server.py`` does — registry,
enforcer with an audit emitter, ``build_mcp_server`` — and then awaits
``mcp.list_tools()``. Nothing is read from the network or a database, and no
tool is ever executed: the enforcer is wired to a stub that refuses calls.
Enumerating after construction matters because ``bind_declared_schemas``
replaces each advertised input schema with the registry's canonical descriptor.

Hash rule: the schema is deep-copied with every string-valued ``"title"`` key
removed — Pydantic derives titles from class and function names, so a rename
moves them without changing the contract — then serialized as
``json.dumps(schema, sort_keys=True, separators=(",", ":"), ensure_ascii=False)``
and hashed with SHA-256. The description is hashed by the same function over the
exact published text, because a model reads that text as instructions. The
schemas and the description are hashed, never the response bodies.

``--check`` reports, naming the tool:

- ``missing-tool`` / ``stale-tool``: the published and recorded name sets
  differ, so a tool was added, removed, or renamed;
- ``schema-drift``: a recorded ``input_schema_sha256``/``output_schema_sha256``
  differs from the schema the service publishes now;
- ``description-drift``: a recorded ``description_sha256`` differs from the
  description the service publishes now, so the text a model reads was rewritten
  without the record — including with injected instructions;
- ``invalid-record``: a recorded hash does not match the recorded schema body,
  so the row was hand-edited;
- ``invalid-field``: a recorded boolean field carries a non-boolean value, so
  ``"deprecated": "true"`` cannot pass as ``True``;
- ``duplicate-tool``: one tool is recorded twice, which would let a malformed
  earlier row hide behind a later one;
- ``version-drift`` / ``undeclared-version``: the declared tool version moved
  without the record, or the service publishes a tool that declares none;
- ``deprecated-tool``: a recorded tool is marked deprecated. A deprecated tool
  is removed from the surface and the record regenerated, never shipped with
  ``deprecated: true``;
- ``stability-drift``: a row claims a stability other than the ``beta`` this
  checker records, so a promotion has to change the code and the status ledger,
  not just the JSON;
- ``schema-mismatch``: the record was written by another version of this
  checker, so its comparison rules cannot be trusted.

A differing ``generator`` is a warning, not a failure: a Python, ``mcp``, or
Pydantic bump changes the runtime identities without changing the contract.
``--update`` replaces the record atomically and leaves it at mode 0644 like its
neighbours, so a committed record is readable.

Every tool is recorded with ``stability: "beta"``: this service's surface is
provisional, and the record says so rather than implying stable support. That
claim lives in ``engineering/architecture-v2/00-status-and-evidence.md`` and is
not upgraded here.
"""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import os
import platform
import sys
import tempfile
from collections.abc import Mapping
from importlib import metadata
from pathlib import Path
from typing import Any, Final

import pydantic
from mcp import types
from mcp.server.fastmcp import FastMCP
from mcp_gateway import (
    BitmapPolicyEvaluator,
    EnforcerOptions,
    GatewayEnforcer,
    InMemoryAuditEmitter,
    ToolContext,
)

from app.server import McpServerWiring, build_mcp_server
from app.tools import build_registry

DESCRIPTOR_SCHEMA: Final = "ibex.mcp-tool-descriptor.v1"
DESCRIPTOR_PATH: Final = Path(__file__).resolve().parents[1] / "mcp_tools.json"
GENERATOR_COMMAND: Final = "python -m app.descriptors --update"
STABILITY: Final = "beta"
SCHEMA_FIELDS: Final = ("input", "output")


def generator() -> dict[str, str]:
    """Identify what wrote the record, so a reader knows which runtime produced it."""
    return {
        "schema": DESCRIPTOR_SCHEMA,
        "command": GENERATOR_COMMAND,
        "python": platform.python_version(),
        "mcp": metadata.version("mcp"),
        "pydantic": pydantic.VERSION,
    }


def canonical_sha256(value: object) -> str:
    """SHA-256 over the title-free canonical JSON form of a schema or description."""
    canonical = json.dumps(
        _without_titles(value), sort_keys=True, separators=(",", ":"), ensure_ascii=False
    )
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def export() -> dict[str, Any]:
    """Return the record for the surface published right now (what ``--update`` writes)."""
    published = sorted(asyncio.run(_published_tools()), key=lambda tool: tool.name)
    versions = _versions()
    return {
        "generator": generator(),
        "tools": [_record(tool, versions.get(tool.name, "")) for tool in published],
    }


def check(path: Path = DESCRIPTOR_PATH) -> list[str]:
    """Return every drift failure between the record and the surface; print warnings."""
    record, failures = _load(path)
    if failures:
        return failures
    published = export()
    _warn_generator(record["generator"], published["generator"])
    rows, row_failures = _rows(record["tools"])
    return row_failures + _drift_failures(rows, published["tools"])


def update(path: Path = DESCRIPTOR_PATH) -> int:
    """Rewrite the record from the current surface, atomically; return the tool count."""
    record = export()
    _refuse_undeclared_versions(record["tools"])
    _write_atomic(path, record)
    return len(record["tools"])


def _refuse_undeclared_versions(tools: list[dict[str, Any]]) -> None:
    """A record must not store an empty version: that is a contract gap, not a row."""
    undeclared = [str(row.get("name")) for row in tools if not row.get("version")]
    if undeclared:
        raise SystemExit(f"published tool(s) with no declared version: {', '.join(undeclared)}")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Record or check the MCP tool descriptors this service publishes.",
        epilog=(
            "--check is the default and never writes. --update replaces the record "
            "atomically and is the only writer."
        ),
    )
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument(
        "--check", action="store_true", help="check the committed record (the default)"
    )
    mode.add_argument("--update", action="store_true", help="rewrite the record from the surface")
    parser.add_argument("--path", type=Path, default=DESCRIPTOR_PATH)
    args = parser.parse_args(argv)

    if args.update:
        print(f"recorded {update(args.path)} tool(s) in {args.path}")
        return 0

    failures = check(args.path)
    for failure in failures:
        print(failure, file=sys.stderr)
    if failures:
        print(f"mcp tool descriptor check failed: {len(failures)} problem(s) in {args.path}")
        return 1
    print(f"mcp tool descriptors match the published surface: {args.path}")
    return 0


async def _published_tools() -> list[types.Tool]:
    return await _build_server().list_tools()


def _build_server() -> FastMCP:
    """Build the daemon the way the server tests do, with a stub that refuses every call."""
    registry = build_registry()
    enforcer = GatewayEnforcer(
        registry,
        _refuse_call,
        options=EnforcerOptions(policy=BitmapPolicyEvaluator(), audit=InMemoryAuditEmitter()),
    )
    return build_mcp_server(McpServerWiring(enforcer=enforcer, registry=registry))


async def _refuse_call(ctx: ToolContext, args: Mapping[str, Any]) -> Mapping[str, Any]:
    raise RuntimeError("descriptor enumeration must not execute a tool")


def _versions() -> dict[str, str]:
    """Declared version per tool, from the registry that owns both schema and version."""
    return {spec.name: spec.version for spec in build_registry().specs()}


def _record(tool: types.Tool, version: str) -> dict[str, Any]:
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


def _without_titles(value: object) -> object:
    """Drop string-valued ``title`` keys at every depth; keep a *property* named title."""
    if isinstance(value, dict):
        kept = {key: item for key, item in value.items() if not _is_title(key, item)}
        return {key: _without_titles(item) for key, item in kept.items()}
    if isinstance(value, list):
        return [_without_titles(item) for item in value]
    return value


def _is_title(key: object, value: object) -> bool:
    return key == "title" and isinstance(value, str)


def _load(path: Path) -> tuple[dict[str, Any], list[str]]:
    """Read the record and validate the outer shape the comparison depends on."""
    if not path.exists():
        return {}, [f"missing-descriptor: {path} does not exist; run {GENERATOR_COMMAND}"]
    try:
        record = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        return {}, [f"unreadable-descriptor: {path}: {error}"]
    if not isinstance(record, dict):
        return {}, ["invalid-descriptor: the record must be a JSON object"]
    failures = _record_failures(record)
    if failures:
        return {}, failures
    return record, []


def _record_failures(record: dict[str, Any]) -> list[str]:
    generator_entry = record.get("generator")
    if not isinstance(generator_entry, dict):
        return ['invalid-descriptor: the record needs a "generator" object']
    if generator_entry.get("schema") != DESCRIPTOR_SCHEMA:
        return [
            (
                "schema-mismatch: the record declares generator.schema "
                f"{generator_entry.get('schema')!r}; this checker reads {DESCRIPTOR_SCHEMA!r}"
            )
        ]
    if not isinstance(record.get("tools"), list):
        return ['invalid-descriptor: the record needs a "tools" array']
    return []


def _rows(recorded: list[object]) -> tuple[dict[str, dict[str, Any]], list[str]]:
    """Index recorded rows by tool name; report rows that cannot be indexed or repeat."""
    rows: dict[str, dict[str, Any]] = {}
    seen: set[str] = set()
    failures: list[str] = []
    for index, row in enumerate(recorded):
        name = row.get("name") if isinstance(row, dict) else None
        if not isinstance(name, str) or not name:
            failures.append(f'invalid-record: tools[{index}] needs a non-empty "name"')
            continue
        if name in seen:
            failures.append(
                f"duplicate-tool: tools[{index}] records {name!r} twice; one row per tool, "
                f"so a malformed row cannot hide behind a later one"
            )
            continue
        seen.add(name)
        field_failure = _field_failure(name, row)
        if field_failure is not None:
            failures.append(field_failure)
        rows[name] = row
    return rows, failures


def _field_failure(name: str, row: dict[str, Any]) -> str | None:
    """Type-check the fields the comparison reads, so a truthy string cannot pass."""
    deprecated = row.get("deprecated")
    if isinstance(deprecated, bool):
        return None
    return (
        f'invalid-field: {name} records "deprecated" as {deprecated!r}; it must be a JSON '
        f"boolean (a deprecated tool is removed from the surface, never shipped)"
    )


def _warn_generator(recorded: object, current: dict[str, str]) -> None:
    """A generator difference is runtime identity only, so it never fails the check."""
    if recorded == current:
        return
    print(
        f"warning: generator differs from this runtime (recorded {recorded}, current {current}); "
        f"the tool contract is unchanged. Run {GENERATOR_COMMAND} to refresh it.",
        file=sys.stderr,
    )


def _drift_failures(rows: dict[str, dict[str, Any]], published: list[dict[str, Any]]) -> list[str]:
    """One comparison per name in sorted order, so the report is deterministic."""
    current = {row["name"]: row for row in published}
    failures: list[str] = []
    for name in sorted(set(current) | set(rows)):
        failures.extend(_tool_failures(name, rows.get(name), current.get(name)))
    return failures


def _tool_failures(
    name: str,
    recorded: dict[str, Any] | None,
    published: dict[str, Any] | None,
) -> list[str]:
    if recorded is None:
        return [f"missing-tool: {name} is published but not recorded; run {GENERATOR_COMMAND}"]
    if published is None:
        return [
            (
                f"stale-tool: {name} is recorded but no longer published (removed or renamed); "
                f"run {GENERATOR_COMMAND}"
            )
        ]
    if recorded.get("deprecated") is True:
        return [
            (
                f"deprecated-tool: {name} is published and recorded as deprecated; remove it "
                f"from the surface and run {GENERATOR_COMMAND}"
            )
        ]
    failures = _version_failures(name, recorded, published)
    if recorded.get("stability") != STABILITY:
        failures.append(
            f"stability-drift: {name} is recorded as {recorded.get('stability')!r}; this "
            f"checker records {STABILITY!r}"
        )
    failures.extend(_description_failures(name, recorded, published))
    for field in SCHEMA_FIELDS:
        failures.extend(_schema_failures(name, field, recorded, published))
    return failures


def _description_failures(
    name: str, recorded: dict[str, Any], published: dict[str, Any]
) -> list[str]:
    """The advertised description is model-visible text, so its hash is pinned too."""
    stored = recorded.get("description_sha256")
    live = published["description_sha256"]
    if stored == live:
        return []
    return [
        (
            f"description-drift: {name} description changed (recorded {_short(stored)}, "
            f"published {_short(live)}); the model reads this text, so review it, then run "
            f"{GENERATOR_COMMAND}"
        )
    ]


def _version_failures(name: str, recorded: dict[str, Any], published: dict[str, Any]) -> list[str]:
    """The recorded version must be declared and must match what the service publishes."""
    live = published["version"]
    if not live:
        return [
            (
                f"undeclared-version: {name} is published with no declared version; declare "
                f"one before recording it with {GENERATOR_COMMAND}"
            )
        ]
    if recorded.get("version") == live:
        return []
    return [
        (
            f"version-drift: {name} is recorded as version {recorded.get('version')!r} but "
            f"publishes {live!r}; run {GENERATOR_COMMAND}"
        )
    ]


def _schema_failures(
    name: str, field: str, recorded: dict[str, Any], published: dict[str, Any]
) -> list[str]:
    """One schema field must be self-consistent and equal the published schema."""
    key = f"{field}_schema_sha256"
    stored = recorded.get(key)
    recomputed = canonical_sha256(recorded.get(f"{field}_schema"))
    if stored != recomputed:
        return [
            (
                f"invalid-record: {name} {key} does not match its recorded {field}_schema "
                f"(row {_short(stored)}, schema {_short(recomputed)}); run {GENERATOR_COMMAND}"
            )
        ]
    live = published[key]
    if stored == live:
        return []
    return [
        (
            f"schema-drift: {name} {field} schema changed (recorded {_short(stored)}, "
            f"published {_short(live)}); review the change, then run {GENERATOR_COMMAND}"
        )
    ]


def _short(digest: object) -> str:
    """The first twelve hex characters of a hash, for a message a human can compare."""
    return str(digest)[:12]


def _write_atomic(path: Path, record: dict[str, Any]) -> None:
    """Replace the record atomically so an interrupted run cannot truncate it."""
    payload = json.dumps(record, indent=2, sort_keys=True, ensure_ascii=False) + "\n"
    path.parent.mkdir(parents=True, exist_ok=True)
    handle, temp_name = tempfile.mkstemp(dir=path.parent, prefix=f".{path.name}.", suffix=".tmp")
    try:
        with os.fdopen(handle, "w", encoding="utf-8") as stream:
            stream.write(payload)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temp_name, path)
        os.chmod(path, 0o644)
    except BaseException:
        Path(temp_name).unlink(missing_ok=True)
        raise


if __name__ == "__main__":
    raise SystemExit(main())
