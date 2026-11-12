"""Check the mounted REST route registry (P0-14 / W5.3).

Every route mounted by ``services/api`` must have exactly one row in
``engineering/architecture-v2/contracts/rest-route-registry.json``. The registry
records ownership, compatibility class, and status only; authentication and
permission data stays in ``services/api/app/route_policy_data.py``.

Contract ID derivation (one rule, applied mechanically)::

    <surface>.<resource>.<action>.v1

- ``surface``: ``operator`` for ``/v1/operator/...``, ``management`` for any
  other ``/v1/...`` route, ``platform`` for unversioned operational routes
  (``/health``, ``/metrics``, ``/docs``, ...).
- ``scope``: a leading static segment immediately followed by a ``{param}``
  segment, e.g. ``organizations`` in ``/v1/organizations/{org_id}/...``. It is
  dropped from the resource and only used as the fallback resource name.
- ``resource``: the remaining static path segments, joined with ``-``. A
  trailing segment that is a registered action verb (``login``, ``activate``,
  ``health``, ...) becomes the action instead, but only when another static
  segment or a scope remains, so ``/health`` keeps ``health`` as its resource.
- ``action``: the trailing action verb when one was removed, otherwise
  ``GET`` -> ``read`` (or ``get`` when the path ends with a parameter),
  ``POST`` -> ``create``, ``PATCH`` -> ``update``, ``PUT`` -> ``replace``,
  ``DELETE`` -> ``delete``.

A new trailing action verb must be added to ``ACTION_VERBS``; until it is, the
segment is treated as a resource (``POST /v1/agents/{id}/resume`` derives
``management.resume.create.v1``). Adding a verb never changes an existing ID
unless an existing route already ends with that segment, and ``--check`` fails
if the registry and this document disagree.

Examples: ``GET /v1/agents`` -> ``management.agents.read.v1``;
``GET /v1/agents/{agent_id}`` -> ``management.agents.get.v1``;
``POST /v1/agents/{agent_id}/activate`` -> ``management.agents.activate.v1``;
``GET /v1/organizations/{org_id}/capture-policies`` ->
``management.capture-policies.read.v1``;
``GET /v1/operator/platform/health`` -> ``operator.platform.health.v1``.

``--check`` (the default; it can also be spelled explicitly, and it is mutually
exclusive with ``--write``) fails on: a mounted route with no row, a row whose key
is no longer mounted, duplicate keys or contract IDs, a row still marked
``unregistered``, an ``owner`` still holding the ``UNASSIGNED`` scaffold sentinel,
an ``evidence`` path that is not a regular file resolving inside the repository
root (a missing path, a directory, an absolute path outside the tree, a ``../``
escape, or an escaping symlink all fail), an unknown
``stability``/``status`` value, a ``contract_id`` that does not match the
derivation above, a ``contract_id`` that does not appear in the contract document
given by ``--doc``, and a protobuf service under ``packages/proto/proto`` that is
neither registered in ``out_of_scope.grpc.registered_services`` nor listed in
``out_of_scope.grpc.declared_out``.

``--write`` scaffolds missing keys only, and a scaffold cannot be laundered into
a claim. Every new row is written with ``"owner": "UNASSIGNED"``, the
conservative ``"stability": "internal"``, ``"status": "unregistered"``, and the
router source from the inventory as ``evidence``. Nothing about ownership,
compatibility class, or shipped status is inferred, so ``--check`` keeps failing
until a human sets a real ``owner``, reviews ``stability``, records ``status``,
and points ``evidence`` at a file that exists. ``--write`` never edits the
contract document, and it writes atomically (temp file plus ``os.replace``), so an
interrupted run cannot truncate the registry.

``status: "shipped"`` means only "mounted in this tree". It is not an acceptance
or support claim; accepted and supported status stays with
``engineering/architecture-v2/00-status-and-evidence.md``.

No network access, no third-party dependency, deterministic output.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Final

REPO_ROOT: Final = Path(__file__).resolve().parents[3]

SCHEMA: Final = "ibex.contract-registry.v1"
REQUIRED_FIELDS: Final = ("key", "contract_id", "owner", "stability", "status", "evidence")
STABILITIES: Final = frozenset({"stable", "beta", "internal"})
STATUSES: Final = frozenset({"shipped", "deprecated", "unregistered"})
METHODS: Final = frozenset({"GET", "POST", "PATCH", "PUT", "DELETE"})
METHOD_ACTIONS: Final = {
    "POST": "create",
    "PATCH": "update",
    "PUT": "replace",
    "DELETE": "delete",
}
ACTION_VERBS: Final = frozenset(
    {
        "activate",
        "archive",
        "clear",
        "health",
        "login",
        "logout",
        "me",
        "pause",
        "ping",
        "query",
        "refresh",
        "resolved",
        "stream",
        "summary",
        "suspend",
        "versions",
    }
)
SCAFFOLD_OWNER: Final = "UNASSIGNED"
SCAFFOLD_STABILITY: Final = "internal"
DEFAULT_EVIDENCE: Final = "services/api/app/main.py"
DOC_ID_PATTERN: Final = re.compile(r"[a-z][a-z0-9-]*(?:\.[a-z0-9-]+)*\.v1")
PROTO_PACKAGE_PATTERN: Final = re.compile(r"^package\s+([\w.]+)\s*;", re.MULTILINE)
PROTO_SERVICE_PATTERN: Final = re.compile(r"^service\s+(\w+)\s*\{", re.MULTILINE)


@dataclass(frozen=True)
class RegistryPaths:
    """Inputs of the check; all overridable so tests never touch the tree."""

    inventory: Path = REPO_ROOT / "services/api/scripts/route_inventory.json"
    registry: Path = REPO_ROOT / "engineering/architecture-v2/contracts/rest-route-registry.json"
    doc: Path = REPO_ROOT / "engineering/architecture-v2/03-contract-registry.md"
    proto_root: Path = REPO_ROOT / "packages/proto/proto"
    root: Path = REPO_ROOT


DEFAULT_PATHS: Final = RegistryPaths()


@dataclass(frozen=True)
class _RouteKey:
    """A registry key that has been split into a method and a mounted path."""

    key: str
    method: str
    path: str

    @classmethod
    def parse(cls, key: str) -> _RouteKey | None:
        method, _, path = key.partition(" ")
        if method not in METHODS:
            return None
        if not path.startswith("/"):
            return None
        return cls(key=key, method=method, path=path)


@dataclass(frozen=True)
class _CheckContext:
    """Inputs every validation helper shares, resolved once per ``check`` run."""

    doc_ids: frozenset[str]
    doc_label: str
    root: Path
    services: dict[str, Path]


_SURFACE_PREFIXES: Final = {"operator": "/v1/operator/", "management": "/v1/"}


def route_key(method: str, path: str) -> str:
    return f"{method} {path}"


def _non_empty_str(value: object) -> bool:
    if not isinstance(value, str):
        return False
    return bool(value)


def _surface(path: str) -> str:
    for surface, prefix in _SURFACE_PREFIXES.items():
        if path.startswith(prefix):
            return surface
    return "platform"


def _path_segments(path: str, surface: str) -> list[str]:
    remainder = path.removeprefix(_SURFACE_PREFIXES.get(surface, "/"))
    return [segment for segment in remainder.split("/") if segment]


def _has_leading_scope(segments: list[str]) -> bool:
    if len(segments) < 2:
        return False
    if segments[0].startswith("{"):
        return False
    return segments[1].startswith("{")


def _scope_and_statics(segments: list[str]) -> tuple[str, list[str]]:
    statics = [segment for segment in segments if not segment.startswith("{")]
    if not _has_leading_scope(segments):
        return "", statics
    return statics.pop(0), statics


def _pop_trailing_action(statics: list[str], scope: str) -> str:
    if not statics:
        return ""
    if statics[-1] not in ACTION_VERBS:
        return ""
    if len(statics) == 1 and not scope:
        return ""
    return statics.pop()


def _resource_name(statics: list[str], scope: str, surface: str) -> str:
    joined = "-".join(statics)
    if joined:
        return joined
    if scope:
        return scope
    return surface


def _action_for(method: str, path: str) -> str:
    if method == "GET":
        return "get" if path.endswith("}") else "read"
    return METHOD_ACTIONS[method]


def derive_contract_id(method: str, path: str) -> str:
    """Derive the one contract ID for a mounted route (see the module docstring)."""
    surface = _surface(path)
    segments = _path_segments(path, surface)
    scope, statics = _scope_and_statics(segments)
    action = _pop_trailing_action(statics, scope)
    resource = _resource_name(statics, scope, surface)
    if not action:
        action = _action_for(method, path)
    return f"{surface}.{resource}.{action}.v1"


def mounted_keys(inventory: object) -> list[str]:
    if not isinstance(inventory, list):
        return []
    keys: set[str] = set()
    for row in inventory:
        keys.update(_row_route_keys(row))
    return sorted(keys)


def _row_route_keys(row: object) -> list[str]:
    if not isinstance(row, dict):
        return []
    path = str(row.get("path", ""))
    return [route_key(str(method), path) for method in row.get("methods", ())]


def _read_json(path: Path, kind: str) -> tuple[object | None, list[str]]:
    if not path.exists():
        return None, [f"missing-{kind}: {path} does not exist"]
    try:
        return json.loads(path.read_text(encoding="utf-8")), []
    except json.JSONDecodeError as error:
        return None, [f"invalid-{kind}: {path}: {error}"]


def load_inventory(path: Path) -> tuple[list[dict[str, object]], list[str]]:
    payload, failures = _read_json(path, "inventory")
    if failures:
        return [], failures
    if not isinstance(payload, list):
        return [], [f"invalid-inventory: {path} must be a JSON array"]
    return [row for row in payload if isinstance(row, dict)], []


def load_registry(path: Path) -> tuple[dict[str, object], list[str]]:
    payload, failures = _read_json(path, "registry")
    if failures:
        return {}, failures
    if not isinstance(payload, dict):
        return {}, [f"invalid-registry: {path} must be a JSON object"]
    return payload, []


def documented_contract_ids(text: str) -> frozenset[str]:
    return frozenset(DOC_ID_PATTERN.findall(text))


def _display_path(path: Path) -> str:
    try:
        return path.relative_to(REPO_ROOT).as_posix()
    except ValueError:
        return path.as_posix()


def _root_label(root: Path) -> str:
    """Name the resolution root for failure messages without printing a bare dot."""
    relative = _display_path(root)
    return "the repository root" if relative in {".", ""} else relative


def _evidence_failure(evidence: str, root: Path) -> str | None:
    """Return the rule ``evidence`` breaks, or ``None`` when it is a usable citation.

    Three rules, checked in this order, so the message names the one that failed:

    1. it resolves inside ``root``: a relative path resolves under ``root``, and an
       absolute path outside the tree, a ``../`` escape, or a symlink pointing
       outside the tree is rejected;
    2. it exists;
    3. it is a regular file, not a directory.
    """
    root_resolved = root.resolve()
    resolved = _resolve_evidence(evidence, root)
    if resolved is None:
        return "cannot be resolved"
    if not resolved.is_relative_to(root_resolved):
        return (
            f"resolves outside {_root_label(root)}; evidence must cite a file inside the repository"
        )
    return _evidence_file_failure(resolved, root)


def _resolve_evidence(evidence: str, root: Path) -> Path | None:
    candidate = Path(evidence)
    if not candidate.is_absolute():
        candidate = root / candidate
    try:
        return candidate.resolve()
    except OSError:
        return None


def _evidence_file_failure(resolved: Path, root: Path) -> str | None:
    if not resolved.exists():
        return f"does not exist under {_root_label(root)}"
    if resolved.is_file():
        return None
    kind = "a directory" if resolved.is_dir() else "not a regular file"
    return f"is not a file (it is {kind})"


def proto_services(proto_root: Path) -> dict[str, Path]:
    """Map fully-qualified protobuf service name to its source file."""
    services: dict[str, Path] = {}
    if not proto_root.is_dir():
        return services
    for source in sorted(proto_root.rglob("*.proto")):
        text = source.read_text(encoding="utf-8")
        package_match = PROTO_PACKAGE_PATTERN.search(text)
        package = package_match.group(1) if package_match else ""
        for name in PROTO_SERVICE_PATTERN.findall(text):
            services[f"{package}.{name}" if package else name] = source
    return services


def _row_shape_failures(row: dict[str, object], label: str) -> list[str]:
    """Field rules: every required field present, no unknown field, none empty."""
    failures: list[str] = []
    missing = [field for field in REQUIRED_FIELDS if field not in row]
    unknown = sorted(set(row) - set(REQUIRED_FIELDS))
    if missing:
        failures.append(f"missing-field: {label} lacks {', '.join(missing)}")
    if unknown:
        failures.append(f"unknown-field: {label} has {', '.join(unknown)}")
    empty = [
        field for field in REQUIRED_FIELDS if isinstance(row.get(field), str) and not row[field]
    ]
    if empty:
        failures.append(f"empty-field: {label} has empty {', '.join(empty)}")
    return failures


def _row_enum_failures(row: dict[str, object], key: str) -> list[str]:
    """The two closed vocabularies a row must draw from."""
    failures: list[str] = []
    stability = row.get("stability")
    if stability not in STABILITIES:
        failures.append(
            f"unknown-enum: {key} has stability {stability!r}; expected one of {sorted(STABILITIES)}"
        )
    status = row.get("status")
    if status not in STATUSES:
        failures.append(
            f"unknown-enum: {key} has status {status!r}; expected one of {sorted(STATUSES)}"
        )
    return failures


def _row_scaffold_failures(row: dict[str, object], key: str) -> list[str]:
    """A scaffold must not read as a claim: no ``unregistered`` status, no sentinel owner."""
    failures: list[str] = []
    if row.get("status") == "unregistered":
        failures.append(
            f"unregistered: {key} is scaffolded but not registered; record owner, stability, and status"
        )
    if row.get("owner") == SCAFFOLD_OWNER:
        failures.append(
            f"unassigned-owner: {key} still holds the {SCAFFOLD_OWNER} scaffold sentinel; set the real "
            "owner, review stability, record status, and point evidence at a file that exists"
        )
    return failures


def _row_evidence_failures(row: dict[str, object], key: str, context: _CheckContext) -> list[str]:
    evidence = row.get("evidence")
    if not _non_empty_str(evidence):
        return []
    reason = _evidence_failure(str(evidence), context.root)
    if reason is None:
        return []
    return [f"missing-evidence: {key} cites {evidence!r}, which {reason}"]


def _row_contract_failures(
    row: dict[str, object], route: _RouteKey, context: _CheckContext
) -> list[str]:
    """The declared contract ID must equal the derivation and appear in the document."""
    contract_id = row.get("contract_id")
    expected = derive_contract_id(route.method, route.path)
    if contract_id != expected:
        return [
            (
                f"contract-id-mismatch: {route.key} declares {contract_id!r}; "
                f"the documented derivation gives {expected!r}"
            )
        ]
    if expected not in context.doc_ids:
        return [
            f"undocumented-contract: {expected} for {route.key} does not appear in {context.doc_label}"
        ]
    return []


def _row_semantic_failures(
    row: dict[str, object], route: _RouteKey, context: _CheckContext
) -> list[str]:
    failures = _row_enum_failures(row, route.key)
    failures.extend(_row_scaffold_failures(row, route.key))
    failures.extend(_row_evidence_failures(row, route.key, context))
    failures.extend(_row_contract_failures(row, route, context))
    return failures


def _row_failures(row: object, index: int, context: _CheckContext) -> list[str]:
    label = f"routes[{index}]"
    if not isinstance(row, dict):
        return [f"invalid-row: {label} is not a JSON object"]
    key = row.get("key")
    if isinstance(key, str) and key:
        label = key
    failures = _row_shape_failures(row, label)
    if not _non_empty_str(key):
        return failures + [f'invalid-key: {label} needs a non-empty "key"']
    route = _RouteKey.parse(str(key))
    if route is None:
        return failures + [
            f'invalid-key: {key} must be "<METHOD> <path>" with METHOD in {sorted(METHODS)}'
        ]
    return failures + _row_semantic_failures(row, route, context)


def _surface_entry_failures(out_of_scope: dict[str, object]) -> list[str]:
    """Every out-of-scope surface must state a reason and name its owner item."""
    failures: list[str] = []
    for surface in ("grpc", "mcp_tools"):
        failures.extend(_entry_failures(surface, out_of_scope.get(surface)))
    return failures


def _entry_failures(surface: str, entry: object) -> list[str]:
    if not isinstance(entry, dict):
        return [f"missing-field: out_of_scope.{surface} must be an object"]
    failures = _entry_text_failures(surface, entry)
    if surface == "grpc":
        failures.extend(_grpc_tracked_by_failures(entry.get("tracked_by")))
    return failures


def _entry_text_failures(surface: str, entry: dict[str, object]) -> list[str]:
    failures: list[str] = []
    if not _non_empty_str(entry.get("reason")):
        failures.append(f"empty-field: out_of_scope.{surface}.reason must state the reason")
    if not _non_empty_str(entry.get("tracked_by")):
        failures.append(f"empty-field: out_of_scope.{surface}.tracked_by must name the owner item")
    return failures


def _grpc_tracked_by_failures(tracked_by: object) -> list[str]:
    if tracked_by == "P0-12":
        return []
    return [f"unknown-enum: out_of_scope.grpc.tracked_by is {tracked_by!r}; expected 'P0-12'"]


def _grpc_entry_failures(
    item: object, index: int, context: _CheckContext
) -> tuple[str | None, list[str]]:
    """Validate one ``registered_services`` entry; return its service name and failures.

    ``None`` means the entry named no usable service, so the caller must not count
    it as registered.
    """
    label = f"out_of_scope.grpc.registered_services[{index}]"
    if not isinstance(item, dict):
        return None, [f"invalid-row: {label} is not a JSON object"]
    name = item.get("service")
    if not _non_empty_str(name):
        return None, [f"empty-field: {label}.service must name a protobuf service"]
    return str(name), _grpc_entry_field_failures(item, str(name), label, context)


def _grpc_entry_field_failures(
    item: dict[str, object], name: str, label: str, context: _CheckContext
) -> list[str]:
    failures = _grpc_service_failures(name, context.services)
    failures.extend(_grpc_contract_failures(item.get("contract_id"), name, label, context))
    if not _non_empty_str(item.get("owner")):
        failures.append(f"empty-field: {label}.owner must name the owning service")
    return failures


def _grpc_service_failures(name: str, services: dict[str, Path]) -> list[str]:
    if name in services:
        return []
    return [
        (
            f"stale-proto-registration: {name} is registered but no such service exists under "
            "packages/proto/proto"
        )
    ]


def _grpc_contract_failures(
    contract_id: object, name: str, label: str, context: _CheckContext
) -> list[str]:
    if not _non_empty_str(contract_id):
        return [f"empty-field: {label}.contract_id must name a registered contract"]
    if contract_id in context.doc_ids:
        return []
    return [
        f"undocumented-contract: {contract_id} for {name} does not appear in {context.doc_label}"
    ]


def _grpc_registration_failures(
    registered: list[object], context: _CheckContext
) -> tuple[set[str], list[str]]:
    """Validate every registered gRPC service; return the usable names and failures."""
    names: set[str] = set()
    failures: list[str] = []
    for index, item in enumerate(registered):
        name, entry_failures = _grpc_entry_failures(item, index, context)
        if name is not None:
            names.add(name)
        failures.extend(entry_failures)
    return names, failures


def _unaccounted_service_failures(
    services: dict[str, Path], registered_names: set[str], declared_out: list[object]
) -> list[str]:
    """Every proto service is either registered here or explicitly declared out."""
    failures: list[str] = []
    for name, source in services.items():
        if name in registered_names:
            continue
        if name in declared_out:
            continue
        failures.append(
            f"unaccounted-proto-service: {name} ({_display_path(source)}) is "
            "neither registered in out_of_scope.grpc.registered_services nor listed in "
            "out_of_scope.grpc.declared_out"
        )
    return failures


def _grpc_failures(grpc: dict[str, object], context: _CheckContext) -> list[str]:
    registered = grpc.get("registered_services")
    declared_out = grpc.get("declared_out")
    if not isinstance(registered, list):
        return ["missing-field: out_of_scope.grpc.registered_services must be an array"]
    if not isinstance(declared_out, list):
        return ["missing-field: out_of_scope.grpc.declared_out must be an array"]
    registered_names, failures = _grpc_registration_failures(registered, context)
    failures.extend(_unaccounted_service_failures(context.services, registered_names, declared_out))
    return failures


def _out_of_scope_failures(registry: dict[str, object], context: _CheckContext) -> list[str]:
    out_of_scope = registry.get("out_of_scope")
    if not isinstance(out_of_scope, dict):
        return ['missing-field: registry needs an "out_of_scope" object']
    failures = _surface_entry_failures(out_of_scope)
    grpc = out_of_scope.get("grpc")
    if not isinstance(grpc, dict):
        return failures
    failures.extend(_grpc_failures(grpc, context))
    return failures


def _schema_failures(registry: dict[str, object]) -> list[str]:
    if registry.get("schema") != SCHEMA:
        return [f"unknown-enum: registry schema is {registry.get('schema')!r}; expected {SCHEMA!r}"]
    return []


def _row_key(row: object) -> str | None:
    if not isinstance(row, dict):
        return None
    key = row.get("key")
    if not isinstance(key, str):
        return None
    return key


def _route_row_failures(
    routes: list[object], context: _CheckContext
) -> tuple[dict[str, int], list[str]]:
    """Validate every row; return the first index per key and every failure."""
    rows_by_key: dict[str, int] = {}
    failures: list[str] = []
    for index, row in enumerate(routes):
        failures.extend(_row_failures(row, index, context))
        key = _row_key(row)
        if key is None:
            continue
        if key in rows_by_key:
            failures.append(
                f"duplicate-key: {key} appears at routes[{rows_by_key[key]}] and routes[{index}]"
            )
        else:
            rows_by_key[key] = index
    return rows_by_key, failures


def _unsorted_failures(routes: list[object]) -> list[str]:
    keys = [str(row.get("key", "")) for row in routes if isinstance(row, dict)]
    for expected_index, key in enumerate(sorted(keys)):
        if keys[expected_index] != key:
            return [
                (
                    f"unsorted-registry: routes[{expected_index}] is {key!r}; "
                    f"expected {keys[expected_index]!r} (rows are sorted by key)"
                )
            ]
    return []


def _contract_claim(row: object) -> tuple[str, str] | None:
    if not isinstance(row, dict):
        return None
    contract_id = row.get("contract_id")
    if not _non_empty_str(contract_id):
        return None
    return str(contract_id), str(row.get("key"))


def _duplicate_contract_failures(routes: list[object]) -> list[str]:
    contract_ids: dict[str, str] = {}
    failures: list[str] = []
    for row in routes:
        claim = _contract_claim(row)
        if claim is None:
            continue
        contract_id, key = claim
        if contract_id in contract_ids:
            failures.append(
                f"duplicate-contract: {contract_id} is claimed by {contract_ids[contract_id]} and "
                f"{key}; the derivation must yield one contract per route"
            )
        else:
            contract_ids[contract_id] = key
    return failures


def _missing_registration_failures(mounted: list[str], rows_by_key: dict[str, int]) -> list[str]:
    failures: list[str] = []
    for key in mounted:
        if key in rows_by_key:
            continue
        method, _, path = key.partition(" ")
        failures.append(
            f"missing-registration: {key} is mounted but has no registry row "
            f"(contract_id {derive_contract_id(method, path)!r})"
        )
    return failures


def _stale_registration_failures(mounted: list[str], rows_by_key: dict[str, int]) -> list[str]:
    return [
        f"stale-registration: {key} is registered but not mounted; remove the row"
        for key in rows_by_key
        if key not in mounted
    ]


def _coverage_failures(mounted: list[str], rows_by_key: dict[str, int]) -> list[str]:
    """Every mounted route has a row, and every row is still mounted."""
    failures = _missing_registration_failures(mounted, rows_by_key)
    failures.extend(_stale_registration_failures(mounted, rows_by_key))
    return failures


def check(paths: RegistryPaths = DEFAULT_PATHS) -> list[str]:
    """Return every failure; an empty list means the registry is complete."""
    inventory, failures = load_inventory(paths.inventory)
    registry, registry_failures = load_registry(paths.registry)
    failures = failures + registry_failures
    if failures:
        return sorted(failures)

    failures.extend(_schema_failures(registry))

    doc_text = paths.doc.read_text(encoding="utf-8") if paths.doc.exists() else ""
    doc_ids = documented_contract_ids(doc_text)
    doc_label = _display_path(paths.doc)

    routes = registry.get("routes")
    if not isinstance(routes, list):
        return sorted(failures + ['missing-field: registry needs a "routes" array'])

    context = _CheckContext(
        doc_ids=doc_ids,
        doc_label=doc_label,
        root=paths.root,
        services=proto_services(paths.proto_root),
    )
    mounted = mounted_keys(inventory)
    rows_by_key, row_failures = _route_row_failures(routes, context)
    failures.extend(row_failures)
    failures.extend(_unsorted_failures(routes))
    failures.extend(_duplicate_contract_failures(routes))
    failures.extend(_coverage_failures(mounted, rows_by_key))
    failures.extend(_out_of_scope_failures(registry, context))
    return sorted(failures)


def scaffold_row(method: str, path: str, source: object) -> dict[str, str]:
    """Build the row ``--write`` adds: sentinel owner, conservative stability, unregistered.

    No ownership, compatibility class, or shipped status is inferred from the
    route. ``--check`` rejects the sentinel owner, so a human must replace it.
    """
    return {
        "key": route_key(method, path),
        "contract_id": derive_contract_id(method, path),
        "owner": SCAFFOLD_OWNER,
        "stability": SCAFFOLD_STABILITY,
        "status": "unregistered",
        "evidence": source if isinstance(source, str) and source else DEFAULT_EVIDENCE,
    }


def _write_registry(path: Path, registry: dict[str, object]) -> None:
    """Replace ``path`` atomically so an interrupted run cannot truncate it."""
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = json.dumps(registry, indent=2) + "\n"
    descriptor, temp_name = tempfile.mkstemp(
        dir=path.parent, prefix=f".{path.name}.", suffix=".tmp"
    )
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temp_name, path)
    except BaseException:
        Path(temp_name).unlink(missing_ok=True)
        raise


def _missing_scaffold_rows(
    inventory: list[dict[str, object]], existing: set[str]
) -> list[dict[str, str]]:
    added: list[dict[str, str]] = []
    for row in inventory:
        path = str(row.get("path", ""))
        for method in row.get("methods", ()):
            if route_key(str(method), path) in existing:
                continue
            added.append(scaffold_row(str(method), path, row.get("source")))
    return added


def _default_out_of_scope() -> dict[str, object]:
    return {
        "grpc": {
            "reason": "gRPC request/response shapes are governed by buf-breaking (W5.1) and P0-12; this registry only accounts for each proto service.",
            "tracked_by": "P0-12",
            "registered_services": [],
            "declared_out": [],
        },
        "mcp_tools": {
            "reason": "MCP tool schemas are versioned descriptors checked by the descriptor diff (W5.5).",
            "tracked_by": "W5.5",
        },
    }


def scaffold(paths: RegistryPaths = DEFAULT_PATHS) -> tuple[int, list[str]]:
    """Add unregistered rows for missing keys; return the count and any failures."""
    inventory, failures = load_inventory(paths.inventory)
    registry, registry_failures = load_registry(paths.registry)
    failures = failures + registry_failures
    if failures:
        return 0, sorted(failures)
    routes = registry.get("routes")
    if not isinstance(routes, list):
        routes = []
    existing = {str(row.get("key")) for row in routes if isinstance(row, dict)}
    added = _missing_scaffold_rows(inventory, existing)
    if not added:
        return 0, []
    existing_rows = [row for row in routes if isinstance(row, dict)]
    registry["routes"] = sorted([*existing_rows, *added], key=lambda row: str(row.get("key")))
    registry.setdefault("schema", SCHEMA)
    registry.setdefault("out_of_scope", _default_out_of_scope())
    paths.registry.parent.mkdir(parents=True, exist_ok=True)
    _write_registry(paths.registry, registry)
    return len(added), []


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Check that every mounted REST route is registered, with a derived contract ID "
            "that appears in the contract document."
        ),
        epilog=(
            '--write scaffolds missing keys only, always with owner "UNASSIGNED", stability '
            '"internal", and status "unregistered", so --check still fails until a human sets the '
            "real owner, reviews stability, records status, and cites existing evidence. --write "
            "never edits the contract document."
        ),
    )
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument(
        "--check",
        action="store_true",
        help="check the committed registry (the default when no mode flag is given)",
    )
    mode.add_argument(
        "--write",
        action="store_true",
        help='scaffold missing keys with sentinel owner and status "unregistered", then check',
    )
    parser.add_argument("--inventory", type=Path, default=DEFAULT_PATHS.inventory)
    parser.add_argument("--registry", type=Path, default=DEFAULT_PATHS.registry)
    parser.add_argument("--doc", type=Path, default=DEFAULT_PATHS.doc)
    parser.add_argument("--proto-root", type=Path, default=DEFAULT_PATHS.proto_root)
    args = parser.parse_args(argv)
    paths = RegistryPaths(
        inventory=args.inventory,
        registry=args.registry,
        doc=args.doc,
        proto_root=args.proto_root,
    )

    if args.write:
        added, failures = scaffold(paths)
        for failure in failures:
            print(failure, file=sys.stderr)
        if failures:
            return 1
        print(f"scaffolded {added} unregistered route(s) in {paths.registry}")
        print(
            "each scaffolded row needs a human owner, stability review, status, and existing evidence"
        )
        return 0

    failures = check(paths)
    for failure in failures:
        print(failure, file=sys.stderr)
    if failures:
        print(f"contract registry check failed: {len(failures)} problem(s) in {paths.registry}")
        return 1
    print(f"contract registry is complete: {paths.registry}")
    print('note: status "shipped" means mounted in this tree, not accepted or supported')
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
