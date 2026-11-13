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

Three value objects carry what the comparison needs, so no function has to take
it one field at a time: ``ReadScope`` is where a run may read from,
``Deprecations`` is the live deprecation record, and ``Comparison`` is the record
at the base ref against the record now.

``git show`` is the only git command this module runs, apart from
``rev-parse --show-toplevel`` to locate the repository; both are read-only.
"""

from __future__ import annotations

import json
import subprocess
from dataclasses import dataclass
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


@dataclass(frozen=True, slots=True)
class ReadScope:
    """Where one run may read from: the allowed root and the deprecation record.

    Both are optional. ``allow_root`` widens the tree the record path must stay
    inside; ``deprecations`` replaces the deprecation record found beside the
    repository root. They travel together because they are the only two paths a
    caller can substitute, and keeping them one value stops the comparison
    functions from growing a parameter per path.
    """

    allow_root: Path | None = None
    deprecations: Path | None = None


@dataclass(frozen=True, slots=True)
class Deprecations:
    """A live deprecation record: the path a failure names and the pairs it covers."""

    path: Path
    covered: frozenset[tuple[str, str]]

    def covers(self, leaf: str, tool: str) -> bool:
        """Whether a live entry authorises changing ``tool`` on the ``leaf`` server."""
        return (leaf, tool) in self.covered


@dataclass(frozen=True, slots=True)
class Comparison:
    """The record at ``base_ref`` against the record now, for one surface.

    ``previous`` and ``current`` are whole records, so the rows are indexed once
    here rather than re-derived for every tool, and every failure the pair
    produces is named with the same ``base_ref`` and deprecation record.
    """

    previous: dict[str, Any]
    current: dict[str, Any]
    surface: Surface
    base_ref: str
    deprecations: Deprecations

    @property
    def leaf(self) -> str:
        """The server name a deprecation entry uses: the record's name without its prefix."""
        return _server_leaf(self.surface.service)

    def failures(self) -> list[str]:
        """Every removal and silent rewrite that no live deprecation entry covers."""
        rows_before = _rows_by_name(self.previous)
        rows_now = _rows_by_name(self.current)
        return [
            failure
            for name in sorted(rows_before)
            for failure in self._row_failures(name, rows_before[name], rows_now)
        ]

    def _row_failures(
        self, name: str, recorded: dict[str, Any], rows_now: dict[str, dict[str, Any]]
    ) -> list[str]:
        """The failures one tool recorded at ``base_ref`` carries."""
        if self.deprecations.covers(self.leaf, name):
            return []
        if name not in rows_now:
            return [self._removal(name)]
        return self._change_failures(name, recorded, rows_now[name])

    def _removal(self, name: str) -> str:
        return (
            f"removed-tool-without-deprecation: {name} was recorded at {self.base_ref} and is gone; "
            f"record a deprecation for it in {self.deprecations.path}"
        )

    def _change_failures(
        self, name: str, recorded: dict[str, Any], current: dict[str, Any]
    ) -> list[str]:
        """One failure per compared field that moved between the two rows."""
        return [
            self._change(name, label)
            for field, label in COMPARED_FIELDS
            if recorded.get(field) != current.get(field)
        ]

    def _change(self, name: str, label: str) -> str:
        return (
            f"schema-change-without-deprecation: {name} {label} changed since {self.base_ref}; "
            f"record a deprecation for it in {self.deprecations.path}"
        )


def check_base(
    surface: Surface,
    path: Path,
    base_ref: str,
    scope: ReadScope | None = None,
) -> list[str]:
    """Compare the record on disk with the record at ``base_ref``; return every failure."""
    read = scope or ReadScope()
    current, failures = load_record(path, read.allow_root)
    if failures:
        return failures
    previous, failures = load_at_ref(path, base_ref, read.allow_root)
    if failures:
        return failures
    deprecations_path = _deprecations_path(path, read)
    deprecations, failures = _deprecations(deprecations_path)
    if failures:
        return failures
    return sorted(Comparison(previous, current, surface, base_ref, deprecations).failures())


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


def _deprecations_path(path: Path, scope: ReadScope) -> Path:
    """The deprecation record: the caller's path, or the one beside the repository root.

    ``load_at_ref`` has already proved git resolves for this path, so the
    repository root is available here without a second failure path.
    """
    if scope.deprecations is not None:
        return scope.deprecations
    toplevel, _failures = git_toplevel(confine(path, scope.allow_root))
    return toplevel / DEPRECATIONS_PATH


def _deprecations(path: Path) -> tuple[Deprecations, list[str]]:
    """The live deprecation record at ``path``; an unreadable one is a named failure."""
    if not path.is_file():
        return Deprecations(path, frozenset()), [
            (
                f"missing-deprecation-record: {path} does not exist; a removed or changed tool "
                "needs a recorded deprecation"
            )
        ]
    entries, failures = _deprecation_entries(path)
    if failures:
        return Deprecations(path, frozenset()), failures
    covered = frozenset(pair for pair in map(_live_pair, entries) if pair is not None)
    return Deprecations(path, covered), []


def _deprecation_entries(path: Path) -> tuple[list[object], list[str]]:
    """The ``entries`` array of the deprecation record, or why it cannot be read."""
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError, RecursionError) as error:
        return [], [f"invalid-deprecation-record: {path}: {error}"]
    entries = payload.get("entries") if isinstance(payload, dict) else None
    if not isinstance(entries, list):
        return [], [f'invalid-deprecation-record: {path} needs an "entries" array']
    return entries, []


def _live_pair(entry: object) -> tuple[str, str] | None:
    """The ``(server-leaf, tool)`` pair one entry covers, or ``None`` when it covers nothing."""
    if not isinstance(entry, dict) or entry.get("surface") != MCP_SURFACE:
        return None
    if entry.get("status") not in LIVE_DEPRECATION_STATUSES:
        return None
    server, tool = entry.get("server"), entry.get("tool")
    if not isinstance(server, str) or not isinstance(tool, str):
        return None
    if not server or not tool:
        return None
    return _server_leaf(server), tool


def _server_leaf(server: str) -> str:
    return server.removeprefix(MCP_SERVER_PREFIX) or server


def _rows_by_name(record: dict[str, Any]) -> dict[str, dict[str, Any]]:
    rows: dict[str, dict[str, Any]] = {}
    for row in record.get("tools", []):
        if isinstance(row, dict) and isinstance(row.get("name"), str):
            rows[row["name"]] = row
    return rows
