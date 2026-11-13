"""The deprecation record's shape: constants, input paths, shared context, and loading.

``check_deprecations.py`` is the CLI; the rules that validate one entry live in the
sibling ``deprecations_*`` modules. This module holds what all of them share: the
schema constants and closed vocabularies, the field set each surface declares, the
input paths, the context resolved once per run, the label and display primitives
every failure message is built from, and the JSON readers for the record and the
two registries.

Standard library only; no network access. Every reader here only reads.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Final

REPO_ROOT: Final = Path(__file__).resolve().parents[3]

SCHEMA: Final = "ibex.deprecations.v1"
SURFACES: Final = frozenset({"rest", "grpc", "mcp", "proxy"})
STABILITIES: Final = frozenset({"stable", "beta"})
STATUSES: Final = frozenset({"proposed", "announced", "withdrawn"})
MCP_SERVERS: Final = frozenset({"operator", "memory"})
WINDOW_DAYS: Final = {"stable": 180, "beta": 31}

ANNOUNCED_FIELD: Final = "announced_on"
COMMON_FIELDS: Final = (
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
# ``announced_on`` is optional: a proposal has not been announced. It is checked
# by the announcement rule, not by presence. ``path`` is optional in the schema
# only so a dedicated rule can reject it on a non-proxy entry; a ``proxy`` entry
# must carry it, and that requirement lives in
# ``deprecations_paths.path_field_failures``.
OPTIONAL_FIELDS: Final = (ANNOUNCED_FIELD, "path")
SELECTORS: Final = {
    "rest": ("contract_id",),
    "grpc": ("contract_id",),
    "mcp": ("tool", "server"),
    # A proxy entry is addressed by ``path``; the dedicated rule owns both its
    # requirement and its grammar, so it is not a required selector here.
    "proxy": (),
}
ALL_SELECTORS: Final = ("contract_id", "tool", "server")
DATE_FIELDS: Final = ("notice_date", "sunset_date")
# Fields validated by a dedicated rule: the enum fields and the boolean have
# their own messages, the date fields have ``invalid-date``, ``announced_on`` has
# the announcement rule (which owns its empty value too), and ``path`` has the
# proxy selector rule (which owns its requirement, type, and grammar).
DEDICATED_FIELDS: Final = frozenset(
    {
        "surface",
        "stability",
        "status",
        "headers_implemented",
        "path",
        *DATE_FIELDS,
        ANNOUNCED_FIELD,
    }
)
# ``rest`` and ``proxy`` can declare headers: both emitters write the standard
# RFC 9745/8594 values. The other two surfaces have no standard deprecation
# header, so their record is the notice of record.
HEADER_SURFACES: Final = frozenset({"rest", "proxy"})
# The statuses an entry can carry before consumers are told, so a REST or proxy
# entry in one of them cannot claim the announcement headers yet.
UNANNOUNCED_STATUSES: Final = frozenset({"proposed", "withdrawn"})


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
class CheckContext:
    """Inputs every entry check shares, resolved once per ``check`` run."""

    rest: dict[str, str]
    rest_label: str
    mcp: dict[str, dict[str, str]]
    mcp_paths: dict[str, Path]
    root: Path
    today: date


def non_empty_str(value: object) -> bool:
    return isinstance(value, str) and bool(value)


def display_path(path: Path) -> str:
    try:
        return path.relative_to(REPO_ROOT).as_posix()
    except ValueError:
        return path.as_posix()


def root_label(root: Path) -> str:
    """Name the resolution root for failure messages without printing a bare dot."""
    relative = display_path(root)
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
        if not isinstance(row, dict) or not non_empty_str(row.get("contract_id")):
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


def mcp_tool_stabilities(path: Path, server: str) -> tuple[dict[str, str] | None, list[str]]:
    """Return ``tool name -> stability`` for one server's committed descriptor."""
    payload, failures = _load_mapping(path, f"mcp-{server}-tools")
    if failures:
        return None, failures
    tools = payload.get("tools")
    if not isinstance(tools, list):
        return None, [f'missing-field: {path} needs a "tools" array']
    stabilities = {
        str(row["name"]): str(row.get("stability"))
        for row in tools
        if isinstance(row, dict) and non_empty_str(row.get("name"))
    }
    return stabilities, []


def mcp_server_path(paths: DeprecationPaths, server: str) -> Path:
    return paths.mcp_root / f"mcp-{server}" / "mcp_tools.json"


def load_mcp_tools(
    paths: DeprecationPaths,
) -> tuple[dict[str, dict[str, str]], dict[str, Path], list[str]]:
    """Return the tools and their stabilities per server, their paths, and any load failures."""
    tools: dict[str, dict[str, str]] = {}
    locations: dict[str, Path] = {}
    failures: list[str] = []
    for server in sorted(MCP_SERVERS):
        path = mcp_server_path(paths, server)
        locations[server] = path
        stabilities, server_failures = mcp_tool_stabilities(path, server)
        failures.extend(server_failures)
        if stabilities is not None:
            tools[server] = stabilities
    return tools, locations, failures


def entry_label(entry: dict[str, object], index: int) -> str:
    return str(entry["id"]) if non_empty_str(entry.get("id")) else f"entries[{index}]"


def required_fields(surface: object) -> tuple[str, ...]:
    return COMMON_FIELDS + SELECTORS.get(str(surface), ALL_SELECTORS)


def entry_fields(surface: object) -> tuple[str, ...]:
    """Every field the surface's schema declares, required and optional."""
    return required_fields(surface) + OPTIONAL_FIELDS


def missing_fields(entry: dict[str, object], fields: tuple[str, ...]) -> list[str]:
    """The declared fields the entry does not carry at all."""
    return [field for field in fields if field not in entry]


def unknown_fields(entry: dict[str, object], fields: tuple[str, ...]) -> list[str]:
    """The entry's fields that the surface's schema does not declare."""
    return sorted(set(entry) - set(fields))


def mistyped_string_fields(entry: dict[str, object], fields: tuple[str, ...]) -> list[str]:
    """The ``string`` fields present with a value of another type.

    Presence is not validity: a field whose schema type is ``string`` must hold a
    string. A ``null`` or an integer would otherwise slip past the emptiness
    check, and the rule that reads the field would treat it as absent. The
    dedicated rules (enum, boolean, date) report their own type failures.
    """
    return [
        field
        for field in fields
        if field in entry and field not in DEDICATED_FIELDS and not isinstance(entry[field], str)
    ]


def empty_string_fields(entry: dict[str, object], fields: tuple[str, ...]) -> list[str]:
    """The ``string`` fields present as the empty string.

    ``announced_on`` is excluded: the announcement rule reports its empty value
    as an invalid date, which is the actionable message for that field. ``path``
    is excluded for the same reason: the proxy selector rule owns its empty
    value, so an empty path on a non-proxy entry stays a single ``unknown-field``
    and on a proxy entry stays a single ``empty-field``.
    """
    return [
        field
        for field in fields
        if field not in {ANNOUNCED_FIELD, "path"}
        and isinstance(entry.get(field), str)
        and not entry[field]
    ]
