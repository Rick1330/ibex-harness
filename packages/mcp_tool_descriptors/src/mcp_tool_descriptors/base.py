"""Diff the committed record against the same file at a git ref (P1-02).

``check`` compares the committed record with the surface a service publishes
*now*. It cannot see what the record looked like before, so it cannot tell a
deliberate removal from a forgotten one: deleting a tool from the surface and
regenerating the record passes ``check``. This module closes that gap. Given a
base ref it reads the record *at that ref* with ``git show <ref>:<path>`` — no
checkout, no working-tree mutation — and compares it with the record on disk.

It fails, naming the tool, when:

- ``removed-tool-without-deprecation``: a tool recorded at the base ref is absent
  from the record now, and no deprecation entry covered it at the base ref;
- ``schema-change-without-deprecation``: a tool recorded in both carries a
  different ``version``, description hash, input schema hash, or output schema
  hash, and no live deprecation entry covers it.

An additive change passes: a tool recorded now and not at the base ref is a new
contract, not a broken one.

The two halves of the policy are recorded at different times, so they are read at
different times. A *change* to a tool that is still published is authorised by a live
entry in the record on disk: one in
``engineering/architecture-v2/contracts/deprecations.json`` with ``surface: "mcp"``,
the matching ``server`` (``operator`` or ``memory``) and ``tool``, and ``status``
``proposed`` or ``announced``. A ``withdrawn`` entry authorises nothing.

A *removal* is authorised by the same entry read at the base ref, because the policy
removes a tool and its entry in one change: by the time the tool is gone, the entry
that announced the removal is gone from the record too. That is also the definition
``services/api/scripts/check_deprecations.py`` enforces from the other side — it
rejects a record whose entry names a tool the descriptor no longer records
(``unknown-tool``) — so the two checks cannot disagree about what a completed removal
is. A tool that never existed is never treated as removed: it was not recorded at the
base ref, so no entry there can cover it.

The record itself is validated before any entry is read: the schema id must be
``ibex.deprecations.v1`` and every entry must carry its surface's required fields, so
a malformed entry cannot waive a removal by being skipped.

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
import re
import subprocess  # nosec B404 # the only call is git, run with an argv list and no shell
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Final

from mcp_tool_descriptors.checks import load_record, record_failures
from mcp_tool_descriptors.paths import confine
from mcp_tool_descriptors.record import Surface

DEPRECATIONS_PATH: Final = Path("engineering/architecture-v2/contracts/deprecations.json")
DEPRECATIONS_SCHEMA: Final = "ibex.deprecations.v1"
MCP_SURFACE: Final = "mcp"
LIVE_DEPRECATION_STATUSES: Final = frozenset({"proposed", "announced"})
DEPRECATION_STATUSES: Final = frozenset({"proposed", "announced", "withdrawn"})
MCP_SERVER_PREFIX: Final = "ibex-mcp-"
#: The fields every entry carries, and the selector each surface adds. The record's
#: schema is owned by ``services/api/scripts/deprecations_model.py``; this is the part
#: of it this module needs to refuse a record whose entries cannot be trusted.
COMMON_ENTRY_FIELDS: Final = (
    "id",
    "surface",
    "stability",
    "notice_date",
    "sunset_date",
    "status",
    "successor",
    "headers_implemented",
    "evidence",
)
ENTRY_SELECTORS: Final = {
    "rest": ("contract_id",),
    "grpc": ("contract_id",),
    "mcp": ("tool", "server"),
    "proxy": ("path",),
}
SURFACES: Final = frozenset(ENTRY_SELECTORS)
#: A ref that names an object: a letter or digit first, then only the characters a
#: branch, tag, or ``refs/...`` path uses. A leading ``-`` is refused, so a caller
#: cannot hand git an option through the ref.
REF_PATTERN: Final = re.compile(r"[A-Za-z0-9][A-Za-z0-9._/-]*")
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
    """The deprecation record: the path a failure names and the pairs it covers.

    Two sets, because the two halves of the policy are recorded at different times.
    ``covered`` is the record on disk: a live entry there authorises a *change* to a
    tool that is still published. ``covered_at_base`` is the same record read at
    ``base_ref``, and it is what authorises a *removal*: the policy removes a tool and
    its entry in one change, so by the time the tool is gone the entry that announced
    the removal is gone from the record too. A record that never named the tool
    authorises nothing, so a tool that never existed is not treated as removed.
    """

    path: Path
    covered: frozenset[tuple[str, str]]
    covered_at_base: frozenset[tuple[str, str]]

    def covers_change(self, leaf: str, tool: str) -> bool:
        """Whether a live entry authorises changing ``tool`` on the ``leaf`` server."""
        return (leaf, tool) in self.covered

    def covers_removal(self, leaf: str, tool: str) -> bool:
        """Whether the entry that announced ``tool``'s removal covered it at ``base_ref``."""
        return (leaf, tool) in self.covered_at_base


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
        if name not in rows_now:
            if self.deprecations.covers_removal(self.leaf, name):
                return []
            return [self._removal(name)]
        if self.deprecations.covers_change(self.leaf, name):
            return []
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
    deprecations, failures = _deprecations(deprecations_path, base_ref, read)
    if failures:
        return failures
    return sorted(Comparison(previous, current, surface, base_ref, deprecations).failures())


def ref_failure(ref: str) -> str | None:
    """Why ``ref`` cannot be handed to git, or ``None`` when it is a plain object name.

    The ref is a caller-supplied string that becomes an argv element, so it is checked
    before git sees it: an empty ref, a leading ``-`` (which git would read as an
    option), whitespace, a ``..`` range, and a trailing ``/`` are all refused.
    """
    if not REF_PATTERN.fullmatch(ref):
        return f"unreadable-base-ref: {ref!r} is not a usable git ref"
    if ".." in ref or ref.endswith("/"):
        return f"unreadable-base-ref: {ref!r} is not a usable git ref"
    return None


def load_at_ref(
    path: Path, ref: str, allow_root: Path | None = None
) -> tuple[dict[str, Any], list[str]]:
    """Read and validate ``<ref>:<path>`` through ``git show`` (never a checkout)."""
    refused = ref_failure(ref)
    if refused is not None:
        return {}, [refused]
    checked = confine(path, allow_root)
    toplevel, failures = git_toplevel(checked)
    if failures:
        return {}, failures
    try:
        relative = checked.relative_to(toplevel)
    except ValueError:
        return {}, [f"unreadable-base-ref: {checked} is outside the git tree at {toplevel}"]
    label = f"{ref}:{relative.as_posix()}"
    output, failures = _git(toplevel, "show", "--end-of-options", label)
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
    """Run one read-only git command; return its stdout or a named failure.

    ``arguments`` is an argv list and never a shell string, and a caller-supplied ref has
    already been checked by ``ref_failure`` and placed after ``--end-of-options``, so git
    cannot read it as an option.
    """
    command = ["git", "-C", str(directory), *arguments]
    try:
        completed = subprocess.run(  # nosec B603 # argv list, no shell, ref pre-checked
            command, capture_output=True, text=True, check=False
        )
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


def _deprecations(path: Path, base_ref: str, scope: ReadScope) -> tuple[Deprecations, list[str]]:
    """The deprecation record at ``path``, and the pairs it covered at ``base_ref``.

    An unreadable, wrongly-schemad, or malformed record is a named failure and covers
    nothing: an entry the module cannot validate must not waive a removal.
    """
    if not path.is_file():
        return _uncovered(path), [
            (
                f"missing-deprecation-record: {path} does not exist; a removed or changed tool "
                "needs a recorded deprecation"
            )
        ]
    entries, failures = _deprecation_entries(path)
    if failures:
        return _uncovered(path), failures
    covered = frozenset(pair for pair in map(_live_pair, entries) if pair is not None)
    return Deprecations(path, covered, _covered_at_base(covered, path, base_ref, scope)), []


def _uncovered(path: Path) -> Deprecations:
    return Deprecations(path, frozenset(), frozenset())


def _covered_at_base(
    covered: frozenset[tuple[str, str]], path: Path, base_ref: str, scope: ReadScope
) -> frozenset[tuple[str, str]]:
    """The pairs the record covered at ``base_ref``, which is what authorises a removal.

    A record that did not exist at that ref, or that cannot be read there, covered
    nothing: a first commit that adds the record is not evidence that any tool was ever
    deprecated. When the caller supplies the record itself (``--deprecations``), that
    record is the notice of record for the run, so it stands for the base-ref one too:
    there is no repository copy to read at the ref.
    """
    if scope.deprecations is not None:
        return covered
    toplevel, failures = git_toplevel(confine(path, scope.allow_root))
    if failures:
        return frozenset()
    try:
        relative = path.relative_to(toplevel).as_posix()
    except ValueError:
        return frozenset()
    output, failures = _git(toplevel, "show", "--end-of-options", f"{base_ref}:{relative}")
    if failures:
        return frozenset()
    entries, _failures = _entries_from_text(output, f"{base_ref}:{relative}")
    return frozenset(pair for pair in map(_live_pair, entries) if pair is not None)


def _deprecation_entries(path: Path) -> tuple[list[object], list[str]]:
    """The ``entries`` array of a valid record, or why the record cannot be trusted."""
    try:
        text = path.read_text(encoding="utf-8")
    except (OSError, UnicodeError) as error:
        return [], [f"invalid-deprecation-record: {path}: {error}"]
    return _entries_from_text(text, path)


def _entries_from_text(text: str, label: str | Path) -> tuple[list[object], list[str]]:
    try:
        payload = json.loads(text)
    except (json.JSONDecodeError, RecursionError) as error:
        return [], [f"invalid-deprecation-record: {label}: {error}"]
    return _entries_from_payload(payload, label)


def _entries_from_payload(payload: object, label: str | Path) -> tuple[list[object], list[str]]:
    """Validate the record's schema and every entry before any entry is read."""
    if not isinstance(payload, dict):
        return [], [f"invalid-deprecation-record: {label} must be a JSON object"]
    schema = payload.get("schema")
    if schema != DEPRECATIONS_SCHEMA:
        return [], [
            (
                f"invalid-deprecation-record: {label}: schema is {schema!r}; "
                f"expected {DEPRECATIONS_SCHEMA!r}"
            )
        ]
    entries = payload.get("entries")
    if not isinstance(entries, list):
        return [], [f'invalid-deprecation-record: {label} needs an "entries" array']
    invalid = [
        f"invalid-deprecation-record: {label}: {reason}"
        for reason in (_entry_failure(entry, index) for index, entry in enumerate(entries))
        if reason is not None
    ]
    return entries, invalid


def _entry_failure(entry: object, index: int) -> str | None:
    """The reason one entry is not a usable record entry, or ``None`` when it is."""
    label = f"entries[{index}]"
    if not isinstance(entry, dict):
        return f"{label} is not a JSON object"
    surface = entry.get("surface")
    if surface not in SURFACES:
        return f"{label} has surface {surface!r}; expected one of {sorted(SURFACES)}"
    required = COMMON_ENTRY_FIELDS + ENTRY_SELECTORS[str(surface)]
    missing = [field for field in required if field not in entry]
    if missing:
        return f"{label} lacks {', '.join(missing)}"
    return _entry_value_failure(entry, label, required)


def _entry_value_failure(
    entry: dict[str, object], label: str, required: tuple[str, ...]
) -> str | None:
    """The value rules: the boolean flag, the non-empty strings, and the status vocabulary."""
    headers = entry["headers_implemented"]
    if not isinstance(headers, bool):
        return f"{label}.headers_implemented must be a boolean, not {headers!r}"
    invalid = [
        field
        for field in required
        if field != "headers_implemented"
        and (not isinstance(entry[field], str) or not entry[field])
    ]
    if invalid:
        return f"{label} has non-string or empty {', '.join(invalid)}"
    if entry["status"] not in DEPRECATION_STATUSES:
        return (
            f"{label} has status {entry['status']!r}; "
            f"expected one of {sorted(DEPRECATION_STATUSES)}"
        )
    return None


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
