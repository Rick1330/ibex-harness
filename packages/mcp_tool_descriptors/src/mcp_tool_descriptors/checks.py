"""The comparison: read the record, validate its shape, report every drift rule.

``check`` is the default mode and never writes. It reports, naming the tool:

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

``update`` is the only writer: it builds the record from the surface and hands it
to the atomic writer, refusing first if any published tool declares no version.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

from mcp_tool_descriptors.hashing import canonical_sha256, short_digest
from mcp_tool_descriptors.paths import confine
from mcp_tool_descriptors.record import (
    DESCRIPTOR_SCHEMA,
    GENERATOR_COMMAND,
    SCHEMA_FIELDS,
    STABILITY,
    Surface,
    build_record,
    refuse_undeclared_versions,
)
from mcp_tool_descriptors.writer import write_atomic


def check(surface: Surface, path: Path, allow_root: Path | None = None) -> list[str]:
    """Return every drift failure between the record and the surface; print warnings."""
    record, failures = _load(path, allow_root)
    if failures:
        return failures
    published = build_record(surface)
    _warn_generator(record["generator"], published["generator"])
    rows, row_failures = _rows(record["tools"])
    return row_failures + _drift_failures(rows, published["tools"])


def update(surface: Surface, path: Path, allow_root: Path | None = None) -> int:
    """Rewrite the record from the current surface, atomically; return the tool count."""
    record = build_record(surface)
    refuse_undeclared_versions(record["tools"])
    write_atomic(path, record, allow_root)
    return len(record["tools"])


def _load(path: Path, allow_root: Path | None = None) -> tuple[dict[str, Any], list[str]]:
    """Read the record and validate the outer shape the comparison depends on."""
    checked = confine(path, allow_root)
    if not checked.is_file():
        return {}, [f"missing-descriptor: {path} does not exist; run {GENERATOR_COMMAND}"]
    try:
        record = json.loads(checked.read_text(encoding="utf-8"))
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
            f"description-drift: {name} description changed (recorded {short_digest(stored)}, "
            f"published {short_digest(live)}); the model reads this text, so review it, then run "
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
                f"(row {short_digest(stored)}, schema {short_digest(recomputed)}); "
                f"run {GENERATOR_COMMAND}"
            )
        ]
    live = published[key]
    if stored == live:
        return []
    return [
        (
            f"schema-drift: {name} {field} schema changed (recorded {short_digest(stored)}, "
            f"published {short_digest(live)}); review the change, then run {GENERATOR_COMMAND}"
        )
    ]
