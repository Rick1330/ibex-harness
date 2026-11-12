"""Check the committed deprecation record (W5.4).

``engineering/architecture-v2/contracts/deprecations.json`` records every
deprecation of a REST contract, a gRPC method, or an MCP tool schema. The policy
it enforces is stated in
``engineering/architecture-v2/16-compatibility-and-versioning.md``: a ``stable``
contract gets **180 days** between its notice and its sunset, a ``beta`` contract
gets **31 days**, and the same window applies to all three surfaces.

The record is the notice of record. An empty ``entries`` array is the correct 1.0
state: nothing is deprecated, and an empty list proves nothing is. An entry is
added only when a deprecation is real, so a phantom deprecation cannot be
committed and a too-short window cannot be announced.

``check`` fails, each with a one-line actionable message, on:

- a ``sunset_date`` that is less than 180 days (``stable``) or 31 days (``beta``)
  after ``notice_date``, or a date field that is present but not an exact
  ``YYYY-MM-DD`` string (``null``, a number, and a list all fail: a value that
  cannot be parsed is not a window, and skipping the window would hide the
  defect);
- a field whose schema type is wrong, not merely empty: a string field that is
  not a string, or a ``successor``/``evidence`` that is a blank string;
- a ``rest`` entry whose ``contract_id`` has no row in
  ``contracts/rest-route-registry.json``, whose recorded ``stability``
  disagrees with that row, or whose ``contract_id`` appears more than once in
  that registry (the loader is not allowed to resolve the contradiction by
  keeping the last row);
- an ``mcp`` entry whose ``server`` is not ``operator`` or ``memory``, or whose
  ``tool`` is absent from that server's committed ``mcp_tools.json``;
- an empty or blank ``successor``, or a ``successor`` that names the contract
  itself;
- ``status: announced`` with ``headers_implemented: false``, with an ``evidence``
  path that is not a string, is blank, does not exist as a file inside the
  repository, or with a ``sunset_date`` already in the past;
- an unknown ``surface``/``stability``/``status`` value, an unknown or missing
  field, a missing or malformed record schema, a duplicate ``id``, or entries
  that are not sorted by ``id``.

A ``grpc`` entry is validated structurally and against the window only. There is
no committed gRPC method registry to cross-check yet: the REST registry declares
gRPC shapes out of scope (``out_of_scope.grpc``), where ``buf-breaking`` (W5.1)
and P0-12 govern them. That gap is stated in the policy document rather than
papered over.

No network access, no third-party dependency, deterministic sorted output. This
script never writes; it only reads the record and the two registries.
"""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import dataclass
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Final

REPO_ROOT: Final = Path(__file__).resolve().parents[3]

SCHEMA: Final = "ibex.deprecations.v1"
SURFACES: Final = frozenset({"rest", "grpc", "mcp"})
STABILITIES: Final = frozenset({"stable", "beta"})
STATUSES: Final = frozenset({"proposed", "announced", "withdrawn"})
MCP_SERVERS: Final = frozenset({"operator", "memory"})
WINDOW_DAYS: Final = {"stable": 180, "beta": 31}

_COMMON_FIELDS: Final = (
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
_SELECTORS: Final = {
    "rest": ("contract_id",),
    "grpc": ("contract_id",),
    "mcp": ("tool", "server"),
}
_ALL_SELECTORS: Final = ("contract_id", "tool", "server")
_DATE_FIELDS: Final = ("notice_date", "sunset_date")
# Fields validated by a dedicated rule: the enum fields and the boolean have
# their own messages, and the date fields have ``invalid-date``.
_DEDICATED_FIELDS: Final = frozenset(
    {"surface", "stability", "status", "headers_implemented", *_DATE_FIELDS}
)


@dataclass(frozen=True)
class DeprecationPaths:
    """Inputs of the check; all overridable so tests never touch the tree."""

    record: Path = REPO_ROOT / "engineering/architecture-v2/contracts/deprecations.json"
    rest_registry: Path = (
        REPO_ROOT / "engineering/architecture-v2/contracts/rest-route-registry.json"
    )
    mcp_root: Path = REPO_ROOT / "services"
    root: Path = REPO_ROOT


DEFAULT_PATHS: Final = DeprecationPaths()


@dataclass(frozen=True)
class _CheckContext:
    """Inputs every entry check shares, resolved once per ``check`` run."""

    rest: dict[str, str]
    rest_label: str
    mcp: dict[str, frozenset[str]]
    mcp_paths: dict[str, Path]
    root: Path
    today: date


def _non_empty_str(value: object) -> bool:
    return isinstance(value, str) and bool(value)


def _display_path(path: Path) -> str:
    try:
        return path.relative_to(REPO_ROOT).as_posix()
    except ValueError:
        return path.as_posix()


def _root_label(root: Path) -> str:
    """Name the resolution root for failure messages without printing a bare dot."""
    relative = _display_path(root)
    return "the repository root" if relative in {".", ""} else relative


def _read_json(path: Path, kind: str) -> tuple[object | None, list[str]]:
    if not path.exists():
        return None, [f"missing-{kind}: {path} does not exist"]
    try:
        return json.loads(path.read_text(encoding="utf-8")), []
    except json.JSONDecodeError as error:
        return None, [f"invalid-{kind}: {path}: {error}"]
    except RecursionError:
        return None, [f"invalid-{kind}: {path}: JSON is nested too deeply to read"]


def _load_mapping(path: Path, kind: str) -> tuple[dict[str, object], list[str]]:
    payload, failures = _read_json(path, kind)
    if failures:
        return {}, failures
    if not isinstance(payload, dict):
        return {}, [f"invalid-{kind}: {path} must be a JSON object"]
    return payload, []


def load_record(path: Path) -> tuple[dict[str, object], list[str]]:
    return _load_mapping(path, "record")


def load_rest_registry(path: Path) -> tuple[dict[str, str], list[str]]:
    """Return ``contract_id -> stability`` for every row in the REST registry.

    A contract may appear once. A duplicate is a contradiction the loader must
    not resolve: keeping the last row would let the record pick whichever
    stability makes its window pass.
    """
    payload, failures = _load_mapping(path, "rest-registry")
    if failures:
        return {}, failures
    routes = payload.get("routes")
    if not isinstance(routes, list):
        return {}, [f'missing-field: {path} needs a "routes" array']
    contracts: dict[str, str] = {}
    first_index: dict[str, int] = {}
    for index, row in enumerate(routes):
        if not isinstance(row, dict) or not _non_empty_str(row.get("contract_id")):
            continue
        contract_id = str(row["contract_id"])
        if contract_id in first_index:
            failures.append(
                f"duplicate-registry-row: {path} lists {contract_id!r} at routes["
                f"{first_index[contract_id]}] and routes[{index}]"
            )
            continue
        first_index[contract_id] = index
        contracts[contract_id] = str(row.get("stability"))
    return contracts, failures


def _mcp_tool_names(path: Path, server: str) -> tuple[frozenset[str] | None, list[str]]:
    payload, failures = _load_mapping(path, f"mcp-{server}-tools")
    if failures:
        return None, failures
    tools = payload.get("tools")
    if not isinstance(tools, list):
        return None, [f'missing-field: {path} needs a "tools" array']
    names = {
        str(row["name"])
        for row in tools
        if isinstance(row, dict) and _non_empty_str(row.get("name"))
    }
    return frozenset(names), []


def mcp_server_path(paths: DeprecationPaths, server: str) -> Path:
    return paths.mcp_root / f"mcp-{server}" / "mcp_tools.json"


def load_mcp_tools(
    paths: DeprecationPaths,
) -> tuple[dict[str, frozenset[str]], dict[str, Path], list[str]]:
    """Return the tools per named server, their paths, and any load failures."""
    tools: dict[str, frozenset[str]] = {}
    locations: dict[str, Path] = {}
    failures: list[str] = []
    for server in sorted(MCP_SERVERS):
        path = mcp_server_path(paths, server)
        locations[server] = path
        names, server_failures = _mcp_tool_names(path, server)
        failures.extend(server_failures)
        if names is not None:
            tools[server] = names
    return tools, locations, failures


def _entry_label(entry: dict[str, object], index: int) -> str:
    return str(entry["id"]) if _non_empty_str(entry.get("id")) else f"entries[{index}]"


def _entry_fields(surface: object) -> tuple[str, ...]:
    return _COMMON_FIELDS + _SELECTORS.get(str(surface), _ALL_SELECTORS)


def _missing_fields(entry: dict[str, object], fields: tuple[str, ...]) -> list[str]:
    """The declared fields the entry does not carry at all."""
    return [field for field in fields if field not in entry]


def _unknown_fields(entry: dict[str, object], fields: tuple[str, ...]) -> list[str]:
    """The entry's fields that the surface's schema does not declare."""
    return sorted(set(entry) - set(fields))


def _mistyped_string_fields(entry: dict[str, object], fields: tuple[str, ...]) -> list[str]:
    """The ``string`` fields present with a value of another type.

    Presence is not validity: a field whose schema type is ``string`` must hold a
    string. A ``null`` or an integer would otherwise slip past the emptiness
    check, and the rule that reads the field would treat it as absent. The
    dedicated rules (enum, boolean, date) report their own type failures.
    """
    return [
        field
        for field in fields
        if field in entry and field not in _DEDICATED_FIELDS and not isinstance(entry[field], str)
    ]


def _empty_string_fields(entry: dict[str, object], fields: tuple[str, ...]) -> list[str]:
    """The ``string`` fields present as the empty string."""
    return [field for field in fields if isinstance(entry.get(field), str) and not entry[field]]


def _field_failures(entry: dict[str, object], label: str, fields: tuple[str, ...]) -> list[str]:
    """Every required field present, no field outside the surface's schema, none empty."""
    failures: list[str] = []
    missing = _missing_fields(entry, fields)
    unknown = _unknown_fields(entry, fields)
    empty = _empty_string_fields(entry, fields)
    if missing:
        failures.append(f"missing-field: {label} lacks {', '.join(missing)}")
    if unknown:
        failures.append(f"unknown-field: {label} has {', '.join(unknown)}")
    if empty:
        failures.append(f"empty-field: {label} has empty {', '.join(empty)}")
    failures.extend(
        f"invalid-field: {label}.{field} must be a string, not {entry[field]!r}"
        for field in _mistyped_string_fields(entry, fields)
    )
    return failures


def _enum_failures(entry: dict[str, object], label: str) -> list[str]:
    failures: list[str] = []
    for field, allowed in (("surface", SURFACES), ("stability", STABILITIES), ("status", STATUSES)):
        value = entry.get(field)
        if isinstance(value, str) and value in allowed:
            continue
        failures.append(
            f"unknown-enum: {label} has {field} {value!r}; expected one of {sorted(allowed)}"
        )
    headers = entry.get("headers_implemented")
    if not isinstance(headers, bool):
        failures.append(
            f"invalid-field: {label}.headers_implemented must be a boolean, not {headers!r}"
        )
    return failures


def _parse_date(value: object) -> date | None:
    """Return the date only for an exact ``YYYY-MM-DD`` string."""
    if not isinstance(value, str):
        return None
    try:
        parsed = date.fromisoformat(value)
    except ValueError:
        return None
    return parsed if parsed.isoformat() == value else None


def _date_failure(entry: dict[str, object], field: str, label: str) -> str | None:
    """Return the failure for a date field that is present but not ``YYYY-MM-DD``.

    Any present value is judged, including a non-string one: ``null`` or an
    integer cannot be parsed, so the window would never be evaluated.
    """
    if field not in entry:
        return None
    value = entry[field]
    if value == "":
        return None
    if _parse_date(value) is not None:
        return None
    return f"invalid-date: {label}.{field} is {value!r}; expected YYYY-MM-DD"


def _date_failures(entry: dict[str, object], label: str) -> list[str]:
    failures: list[str] = []
    for field in _DATE_FIELDS:
        failure = _date_failure(entry, field, label)
        if failure is not None:
            failures.append(failure)
    return failures


def _window_days(entry: dict[str, object]) -> tuple[str, date, date, int] | None:
    """Return the class, notice, sunset, and window length, or ``None`` if unusable."""
    stability = entry.get("stability")
    if not isinstance(stability, str):
        return None
    if stability not in WINDOW_DAYS:
        return None
    notice = _parse_date(entry.get("notice_date"))
    if notice is None:
        return None
    sunset = _parse_date(entry.get("sunset_date"))
    if sunset is None:
        return None
    return str(stability), notice, sunset, (sunset - notice).days


def _window_failures(entry: dict[str, object], label: str) -> list[str]:
    window = _window_days(entry)
    if window is None:
        return []
    stability, notice, sunset, actual = window
    minimum = WINDOW_DAYS[stability]
    if actual >= minimum:
        return []
    return [
        (
            f"window-too-short: {label} is {stability}, so sunset_date {sunset.isoformat()} must be "
            f"at least {minimum} days after notice_date {notice.isoformat()}; this window is "
            f"{actual} day(s)"
        )
    ]


def _contract_target(entry: dict[str, object]) -> str:
    for field in ("contract_id", "tool"):
        value = entry.get(field)
        if _non_empty_str(value):
            return str(value)
    return ""


def _successor_failures(entry: dict[str, object], label: str) -> list[str]:
    successor = entry.get("successor")
    if not _non_empty_str(successor):
        return []
    if not str(successor).strip():
        return [f"empty-field: {label} has empty successor"]
    if successor == _contract_target(entry):
        return [f"successor-is-self: {label} names {successor!r} as its own successor"]
    return []


def _evidence_reason(evidence: str, root: Path) -> str | None:
    """Return the rule ``evidence`` breaks, or ``None`` when it cites a real repository file."""
    if Path(evidence).is_absolute():
        return "is an absolute path; cite a file inside the repository"
    try:
        resolved = (root / evidence).resolve()
    except OSError:
        return "cannot be resolved"
    if not resolved.is_relative_to(root.resolve()):
        return (
            f"resolves outside {_root_label(root)}; evidence must cite a file inside the repository"
        )
    if not resolved.exists():
        return f"does not exist under {_root_label(root)}"
    if not resolved.is_file():
        return "is not a regular file"
    return None


def _evidence_failures(entry: dict[str, object], label: str, context: _CheckContext) -> list[str]:
    evidence = entry.get("evidence")
    if not _non_empty_str(evidence):
        return []
    reason = _evidence_reason(str(evidence), context.root)
    if reason is None:
        return []
    return [f"missing-evidence: {label} cites {evidence!r}, which {reason}"]


def _status_failures(entry: dict[str, object], label: str, context: _CheckContext) -> list[str]:
    """A deprecation may only be announced when it is implemented and still in window."""
    if entry.get("status") != "announced":
        return []
    failures: list[str] = []
    if entry.get("headers_implemented") is not True:
        failures.append(
            f"headers-not-implemented: {label} is announced, so headers_implemented must be true; "
            "implement Deprecation and Sunset before announcing"
        )
    failures.extend(_evidence_failures(entry, label, context))
    sunset = _parse_date(entry.get("sunset_date"))
    if sunset is not None and sunset < context.today:
        failures.append(
            f"sunset-passed: {label} is announced but sunset_date {sunset.isoformat()} is in the "
            "past; withdraw it or record the completed removal"
        )
    return failures


def _rest_failures(entry: dict[str, object], label: str, context: _CheckContext) -> list[str]:
    contract_id = entry.get("contract_id")
    if not _non_empty_str(contract_id):
        return []
    stability = context.rest.get(str(contract_id))
    if stability is None:
        return [
            (
                f"unknown-contract: {label} deprecates {contract_id}, which has no row in "
                f"{context.rest_label}"
            )
        ]
    if stability != entry.get("stability"):
        return [
            (
                f"stability-mismatch: {label} records {entry.get('stability')!r} but "
                f"{context.rest_label} records {stability!r} for {contract_id}"
            )
        ]
    return []


def _unknown_server_failures(label: str, server: object) -> list[str]:
    return [
        (f"unknown-server: {label} names server {server!r}; expected one of {sorted(MCP_SERVERS)}")
    ]


def _mcp_failures(entry: dict[str, object], label: str, context: _CheckContext) -> list[str]:
    server = entry.get("server")
    if not _non_empty_str(server):
        return _unknown_server_failures(label, server)
    if str(server) not in MCP_SERVERS:
        return _unknown_server_failures(label, server)
    tool = entry.get("tool")
    if not _non_empty_str(tool):
        return []
    if str(tool) in context.mcp[str(server)]:
        return []
    return [
        (
            f"unknown-tool: {label} deprecates tool {tool!r}, which is absent from "
            f"{_display_path(context.mcp_paths[str(server)])}"
        )
    ]


def _registry_failures(entry: dict[str, object], label: str, context: _CheckContext) -> list[str]:
    surface = entry.get("surface")
    if surface == "rest":
        return _rest_failures(entry, label, context)
    if surface == "mcp":
        return _mcp_failures(entry, label, context)
    return []


def _entry_failures(entry: object, index: int, context: _CheckContext) -> list[str]:
    if not isinstance(entry, dict):
        return [f"invalid-row: entries[{index}] is not a JSON object"]
    label = _entry_label(entry, index)
    failures = _field_failures(entry, label, _entry_fields(entry.get("surface")))
    failures.extend(_enum_failures(entry, label))
    failures.extend(_date_failures(entry, label))
    failures.extend(_window_failures(entry, label))
    failures.extend(_successor_failures(entry, label))
    failures.extend(_status_failures(entry, label, context))
    failures.extend(_registry_failures(entry, label, context))
    return failures


def _duplicate_id_failures(entries: list[object]) -> list[str]:
    first_index: dict[str, int] = {}
    failures: list[str] = []
    for index, entry in enumerate(entries):
        if not isinstance(entry, dict) or not _non_empty_str(entry.get("id")):
            continue
        entry_id = str(entry["id"])
        if entry_id in first_index:
            failures.append(
                f"duplicate-id: {entry_id} appears at entries[{first_index[entry_id]}] and "
                f"entries[{index}]"
            )
        else:
            first_index[entry_id] = index
    return failures


def _unsorted_failures(entries: list[object]) -> list[str]:
    """Report the first entry out of order, naming what it is and what belongs there."""
    ids = [
        str(entry["id"])
        for entry in entries
        if isinstance(entry, dict) and _non_empty_str(entry.get("id"))
    ]
    for index, expected in enumerate(sorted(ids)):
        if ids[index] != expected:
            return [
                (
                    f"unsorted-record: entries[{index}] is {ids[index]!r}; expected {expected!r} "
                    "(entries are sorted by id)"
                )
            ]
    return []


def _entries_failures(entries: list[object], context: _CheckContext) -> list[str]:
    failures: list[str] = []
    for index, entry in enumerate(entries):
        failures.extend(_entry_failures(entry, index, context))
    failures.extend(_duplicate_id_failures(entries))
    failures.extend(_unsorted_failures(entries))
    return failures


def _schema_failures(record: dict[str, object]) -> list[str]:
    if record.get("schema") != SCHEMA:
        return [f"unknown-enum: record schema is {record.get('schema')!r}; expected {SCHEMA!r}"]
    return []


def _record_has_no_entries(path: Path) -> bool:
    """True only when the record loads cleanly and declares an empty entries array."""
    record, failures = load_record(path)
    return not failures and record.get("entries") == []


def check(paths: DeprecationPaths = DEFAULT_PATHS, today: date | None = None) -> list[str]:
    """Return every failure; an empty list means the record is valid."""
    record, failures = load_record(paths.record)
    rest, rest_failures = load_rest_registry(paths.rest_registry)
    mcp, mcp_paths, mcp_failures = load_mcp_tools(paths)
    failures.extend(rest_failures)
    failures.extend(mcp_failures)
    if failures:
        return sorted(failures)

    failures.extend(_schema_failures(record))
    entries = record.get("entries")
    if not isinstance(entries, list):
        return sorted(failures + ['missing-field: record needs an "entries" array'])

    context = _CheckContext(
        rest=rest,
        rest_label=_display_path(paths.rest_registry),
        mcp=mcp,
        mcp_paths=mcp_paths,
        root=paths.root,
        today=today or datetime.now(UTC).date(),
    )
    failures.extend(_entries_failures(entries, context))
    return sorted(failures)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Check the committed deprecation record against the REST and MCP registries "
            "and the 180-day stable / 31-day beta support window."
        ),
        epilog=(
            "The check mode is the only mode: this script reads the record and the two "
            "registries and never writes. An empty entries array is valid and is the "
            "correct state when nothing is deprecated."
        ),
    )
    parser.add_argument(
        "--check",
        action="store_true",
        help="check the committed record (the default, and the only mode)",
    )
    parser.add_argument(
        "--record",
        type=Path,
        default=DEFAULT_PATHS.record,
        help="path to the deprecation record (input only; never written)",
    )
    parser.add_argument("--rest-registry", type=Path, default=DEFAULT_PATHS.rest_registry)
    parser.add_argument("--mcp-root", type=Path, default=DEFAULT_PATHS.mcp_root)
    parser.add_argument("--root", type=Path, default=DEFAULT_PATHS.root)
    args = parser.parse_args(argv)
    paths = DeprecationPaths(
        record=args.record,
        rest_registry=args.rest_registry,
        mcp_root=args.mcp_root,
        root=args.root,
    )

    failures = check(paths)
    for failure in failures:
        print(failure, file=sys.stderr)
    if failures:
        print(f"deprecation check failed: {len(failures)} problem(s) in {paths.record}")
        return 1
    print(f"deprecation record is valid: {paths.record}")
    if _record_has_no_entries(paths.record):
        print("note: an empty entries array means nothing is deprecated")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
