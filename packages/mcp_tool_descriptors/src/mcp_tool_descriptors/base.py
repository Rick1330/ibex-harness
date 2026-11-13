"""Diff the committed record against the same file at a git ref (P1-02).

``check`` compares the committed record with the surface a service publishes
*now*. It cannot see what the record looked like before, so it cannot tell a
deliberate removal from a forgotten one: deleting a tool from the surface and
regenerating the record passes ``check``. This module closes that gap. Given a
base ref it reads the record *at that ref* with ``git show <ref>:<path>`` — no
checkout, no working-tree mutation — and compares it with the record on disk.

It fails, naming the tool, when:

- ``removed-tool-without-deprecation``: a tool recorded at the base ref is absent
  from the record now, and no live deprecation entry covers it;
- ``schema-change-without-deprecation``: a tool recorded in both carries a
  different ``version``, description hash, input schema hash, or output schema
  hash, and no live deprecation entry covers it.

An additive change passes: a tool recorded now and not at the base ref is a new
contract, not a broken one. A live deprecation entry is one in
``engineering/architecture-v2/contracts/deprecations.json`` with ``surface:
"mcp"``, the matching ``server`` (``operator`` or ``memory``) and ``tool``, and
``status`` ``proposed`` or ``announced``. A ``withdrawn`` entry authorises
nothing.

The comparison is against the committed record, not the live surface, because
the record is the contract artefact that ships. Running ``--check`` first (the
CLI does) proves the record still matches the surface; this mode then proves the
record did not lose or silently rewrite a tool on the way here.

``git show`` is the only git command this module runs, apart from
``rev-parse --show-toplevel`` to locate the repository; both are read-only.
"""

from __future__ import annotations

import json
import subprocess
from pathlib import Path
from typing import Any, Final

from mcp_tool_descriptors.checks import load_record, record_failures
from mcp_tool_descriptors.paths import confine
from mcp_tool_descriptors.record import Surface

DEPRECATIONS_PATH: Final = Path("engineering/architecture-v2/contracts/deprecations.json")
MCP_SURFACE: Final = "mcp"
LIVE_DEPRECATION_STATUSES: Final = frozenset({"proposed", "announced"})
MCP_SERVER_PREFIX: Final = "ibex-mcp-"
#: Recorded field and the name a human reads in the failure message.
COMPARED_FIELDS: Final = (
    ("version", "version"),
    ("description_sha256", "description"),
    ("input_schema_sha256", "input schema"),
    ("output_schema_sha256", "output schema"),
)


def check_base(
    surface: Surface,
    path: Path,
    base_ref: str,
    allow_root: Path | None = None,
    deprecations: Path | None = None,
) -> list[str]:
    """Compare the record on disk with the record at ``base_ref``; return every failure."""
    current, failures = load_record(path, allow_root)
    if failures:
        return failures
    previous, failures = load_at_ref(path, base_ref, allow_root)
    if failures:
        return failures
    deprecations_path = _deprecations_path(path, allow_root, deprecations)
    deprecated, failures = _deprecated_tools(deprecations_path)
    if failures:
        return failures
    return sorted(
        _comparison_failures(previous, current, deprecated, surface, base_ref, deprecations_path)
    )


def load_at_ref(
    path: Path, ref: str, allow_root: Path | None = None
) -> tuple[dict[str, Any], list[str]]:
    """Read and validate ``<ref>:<path>`` through ``git show`` (never a checkout)."""
    checked = confine(path, allow_root)
    toplevel, failures = git_toplevel(checked)
    if failures:
        return {}, failures
    try:
        relative = checked.relative_to(toplevel)
    except ValueError:
        return {}, [f"unreadable-base-ref: {checked} is outside the git tree at {toplevel}"]
    label = f"{ref}:{relative.as_posix()}"
    output, failures = _git(toplevel, "show", label)
    if failures:
        return {}, failures
    return _parse_record(output, label)


def git_toplevel(path: Path) -> tuple[Path, list[str]]:
    """The repository root that owns ``path``."""
    directory = path.parent if path.parent.is_dir() else Path.cwd()
    output, failures = _git(directory, "rev-parse", "--show-toplevel")
    if failures:
        return directory, failures
    return Path(output.strip()), []


def _git(directory: Path, *arguments: str) -> tuple[str, list[str]]:
    """Run one read-only git command; return its stdout or a named failure."""
    command = ["git", "-C", str(directory), *arguments]
    try:
        completed = subprocess.run(command, capture_output=True, text=True, check=False)
    except OSError as error:
        return "", [f"unreadable-base-ref: cannot run {' '.join(command)}: {error}"]
    if completed.returncode == 0:
        return completed.stdout, []
    detail = completed.stderr.strip() or completed.stdout.strip() or "no output"
    return "", [
        f"unreadable-base-ref: {' '.join(command)} failed ({completed.returncode}): {detail}"
    ]


def _parse_record(text: str, label: str) -> tuple[dict[str, Any], list[str]]:
    try:
        record = json.loads(text)
    except (json.JSONDecodeError, RecursionError) as error:
        return {}, [f"unreadable-base-ref: {label}: {error}"]
    if not isinstance(record, dict):
        return {}, [f"invalid-descriptor: {label} must be a JSON object"]
    failures = record_failures(record)
    if failures:
        return {}, [f"{failure} ({label})" for failure in failures]
    return record, []


def _deprecations_path(path: Path, allow_root: Path | None, deprecations: Path | None) -> Path:
    """The deprecation record: the caller's path, or the one beside the repository root.

    ``load_at_ref`` has already proved git resolves for this path, so the
    repository root is available here without a second failure path.
    """
    if deprecations is not None:
        return deprecations
    toplevel, _failures = git_toplevel(confine(path, allow_root))
    return toplevel / DEPRECATIONS_PATH


def _deprecated_tools(path: Path) -> tuple[set[tuple[str, str]], list[str]]:
    """The ``(server-leaf, tool)`` pairs a live deprecation entry covers."""
    if not path.is_file():
        return set(), [
            (
                f"missing-deprecation-record: {path} does not exist; a removed or changed tool "
                "needs a recorded deprecation"
            )
        ]
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError, RecursionError) as error:
        return set(), [f"invalid-deprecation-record: {path}: {error}"]
    entries = payload.get("entries") if isinstance(payload, dict) else None
    if not isinstance(entries, list):
        return set(), [f'invalid-deprecation-record: {path} needs an "entries" array']
    pairs: set[tuple[str, str]] = set()
    for entry in entries:
        if not isinstance(entry, dict) or entry.get("surface") != MCP_SURFACE:
            continue
        server, tool = entry.get("server"), entry.get("tool")
        if not isinstance(server, str) or not isinstance(tool, str) or not server or not tool:
            continue
        if entry.get("status") not in LIVE_DEPRECATION_STATUSES:
            continue
        pairs.add((_server_leaf(server), tool))
    return pairs, []


def _server_leaf(server: str) -> str:
    return server.removeprefix(MCP_SERVER_PREFIX) or server


def _comparison_failures(
    previous: dict[str, Any],
    current: dict[str, Any],
    deprecated: set[tuple[str, str]],
    surface: Surface,
    base_ref: str,
    deprecations: Path,
) -> list[str]:
    rows_before = _rows_by_name(previous)
    rows_now = _rows_by_name(current)
    leaf = _server_leaf(surface.service)
    failures: list[str] = []
    for name in sorted(rows_before):
        if (leaf, name) in deprecated:
            continue
        if name not in rows_now:
            failures.append(
                f"removed-tool-without-deprecation: {name} was recorded at {base_ref} and is gone; "
                f"record a deprecation for it in {deprecations}"
            )
            continue
        failures.extend(
            _changed_field_failures(name, rows_before[name], rows_now[name], base_ref, deprecations)
        )
    return failures


def _rows_by_name(record: dict[str, Any]) -> dict[str, dict[str, Any]]:
    rows: dict[str, dict[str, Any]] = {}
    for row in record.get("tools", []):
        if isinstance(row, dict) and isinstance(row.get("name"), str):
            rows[row["name"]] = row
    return rows


def _changed_field_failures(
    name: str,
    recorded: dict[str, Any],
    current: dict[str, Any],
    base_ref: str,
    deprecations: Path,
) -> list[str]:
    return [
        (
            f"schema-change-without-deprecation: {name} {label} changed since {base_ref}; "
            f"record a deprecation for it in {deprecations}"
        )
        for field, label in COMPARED_FIELDS
        if recorded.get(field) != current.get(field)
    ]
