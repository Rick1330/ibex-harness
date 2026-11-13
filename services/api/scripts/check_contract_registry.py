"""Check the contract registry (P0-14 / W5.3 / W5.5).

Every contract surface shipped in this tree must have exactly one row in
``engineering/architecture-v2/contracts/rest-route-registry.json``:

- ``routes`` — every route mounted by ``services/api`` (REST);
- ``grpc_methods`` — every ``rpc`` declared under ``packages/proto/proto``;
- ``mcp_tools`` — every tool published by the two MCP services and recorded in
  their committed ``mcp_tools.json``.

The registry records ownership, compatibility class, and status only;
authentication and permission data stays in
``services/api/app/route_policy_data.py``.

The registry schema is ``ibex.contract-registry.v2``. Adding the two required
arrays changed the file shape, so the version moved with it; a v1 file is
rejected rather than read with a missing-array failure.

REST contract ID derivation (one rule, applied mechanically)::

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

gRPC method contract ID derivation (``grpc_methods``)::

    grpc.<package-leaf>.<rpc-kebab>.v1

- ``package-leaf``: the last segment of the protobuf package once a trailing
  ``v1`` is dropped — ``ibex.auth.v1`` -> ``auth``, ``ibex.context.v1`` ->
  ``context``.
- ``rpc-kebab``: the rpc name in kebab case — ``ValidateToken`` ->
  ``validate-token``, ``BeginTotpEnrollment`` -> ``begin-totp-enrollment``,
  ``IssuePolicySnapshot`` -> ``issue-policy-snapshot``.

The row ``key`` is the fully-qualified method name
(``ibex.auth.v1.AuthService.ValidateToken``), so a row can only name a method
the proto tree declares. Examples: ``grpc.auth.validate-token.v1``,
``grpc.context.assemble-context.v1``.

MCP tool contract ID derivation (``mcp_tools``)::

    mcp.<server-leaf>.<tool-kebab>.v1

- ``server-leaf``: the FastMCP server name without its ``ibex-mcp-`` prefix —
  ``ibex-mcp-memory`` -> ``memory``, ``ibex-mcp-operator`` -> ``operator``.
- ``tool-kebab``: the advertised tool name with ``.`` and ``_`` folded to ``-``
  — ``budget.get`` -> ``budget-get``, ``search_memory`` -> ``search-memory``.

The row ``key`` is ``<server>/<tool>``, and the ``server`` field repeats the
server, so a row cannot attach a tool to the wrong surface. Examples:
``mcp.operator.budget-get.v1``, ``mcp.memory.search-memory.v1``.

A REST row must also appear in the contract document (``--doc``). gRPC and MCP
rows are not required to: their authoritative source is the proto tree and the
committed descriptor record, which this check reads directly, and documenting
them in ``03-contract-registry.md`` is a separate change.

``--check`` (the default; it can also be spelled explicitly, and it is mutually
exclusive with ``--write``) fails on: a mounted route with no row, a row whose key
is no longer mounted, duplicate keys or contract IDs, a row still marked
``unregistered``, an ``owner`` still holding the ``UNASSIGNED`` scaffold sentinel,
an ``evidence`` path that is not a regular file resolving inside the repository
root (a missing path, a directory, an absolute path outside the tree, a ``../``
escape, or an escaping symlink all fail), an unknown
``stability``/``status`` value, a ``contract_id`` that does not match the
derivation above, a ``contract_id`` that does not appear in the contract document
given by ``--doc``, a protobuf service under ``packages/proto/proto`` that is
neither registered in ``out_of_scope.grpc.registered_services`` nor listed in
``out_of_scope.grpc.declared_out``, an rpc declared in the proto tree with no
``grpc_methods`` row, a ``grpc_methods`` row whose method no longer exists, an
rpc row whose derived ID is not a valid contract ID, a service with method rows
that is not in ``registered_services``, a registered service with no method row,
a service that is both declared out and registered or method-bearing, a tool
recorded in an ``mcp_tools.json`` with no ``mcp_tools`` row, and a ``mcp_tools``
row whose tool is no longer recorded (or whose ``server`` field disagrees with
its key).

The service-level ``out_of_scope.grpc.registered_services`` rows are kept rather
than migrated: ``engineering/architecture-v2/03-contract-registry.md`` names them
as the service accounting point, and the accepted ``principal-context.v1`` shape
is attached there. They are cross-checked against ``grpc_methods`` instead, so
the service index and the method rows cannot disagree. ``declared_out`` remains
the explicit service-level opt-out: a declared-out service carries no method rows
and is exempt from rpc registration.

``--write`` scaffolds missing keys only, and a scaffold cannot be laundered into
a claim. Every new row is written with ``"owner": "UNASSIGNED"``, the
conservative ``"stability": "internal"``, ``"status": "unregistered"``, and the
router source from the inventory as ``evidence``. Nothing about ownership,
compatibility class, or shipped status is inferred, so ``--check`` keeps failing
until a human sets a real ``owner``, reviews ``stability``, records ``status``,
and points ``evidence`` at a file that exists. ``--write`` never edits the
contract document, and it writes atomically (temp file plus ``os.replace``), so an
interrupted run cannot truncate the registry. It scaffolds REST routes only: a
``grpc_methods`` or ``mcp_tools`` row carries the same human decisions and is
added by hand.

``status: "shipped"`` means only "declared, mounted, or recorded in this tree".
It is not an acceptance or support claim; accepted and supported status stays
with ``engineering/architecture-v2/00-status-and-evidence.md``.

No network access, no third-party dependency, deterministic output. The
contract-ID grammar (candidate validation and document extraction) lives in
``contract_ids.py`` beside this script.
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

from contract_ids import documented_contract_ids

REPO_ROOT: Final = Path(__file__).resolve().parents[3]

SCHEMA: Final = "ibex.contract-registry.v2"
REQUIRED_FIELDS: Final = ("key", "contract_id", "owner", "stability", "status", "evidence")
GRPC_METHOD_FIELDS: Final = ("key", "contract_id", "owner", "stability", "status", "evidence")
MCP_TOOL_FIELDS: Final = ("key", "contract_id", "server", "owner", "status", "evidence")
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
PROTO_PACKAGE_PATTERN: Final = re.compile(r"^package\s+([\w.]+)\s*;", re.MULTILINE)
PROTO_SERVICE_PATTERN: Final = re.compile(r"^service\s+(\w+)\s*\{", re.MULTILINE)
PROTO_RPC_PATTERN: Final = re.compile(r"\brpc\s+(\w+)\s*\(")
PROTO_BLOCK_COMMENT: Final = re.compile(r"/\*.*?\*/", re.DOTALL)
PROTO_LINE_COMMENT: Final = re.compile(r"//[^\n]*")
PROTO_VERSION_SEGMENT: Final = "v1"
MCP_SERVER_PREFIX: Final = "ibex-mcp-"
MCP_KEY_SEPARATOR: Final = "/"


@dataclass(frozen=True)
class RegistryPaths:
    """Inputs of the check; all overridable so tests never touch the tree."""

    inventory: Path = REPO_ROOT / "services/api/scripts/route_inventory.json"
    registry: Path = REPO_ROOT / "engineering/architecture-v2/contracts/rest-route-registry.json"
    doc: Path = REPO_ROOT / "engineering/architecture-v2/03-contract-registry.md"
    proto_root: Path = REPO_ROOT / "packages/proto/proto"
    mcp_records: tuple[tuple[str, Path], ...] = (
        ("ibex-mcp-memory", REPO_ROOT / "services/mcp-memory/mcp_tools.json"),
        ("ibex-mcp-operator", REPO_ROOT / "services/mcp-operator/mcp_tools.json"),
    )
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
    rpcs: dict[str, Path]
    mcp_surfaces: dict[str, tuple[Path, frozenset[str]]]


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


def _kebab(name: str) -> str:
    """``BeginTotpEnrollment`` -> ``begin-totp-enrollment`` (acronym-safe)."""
    spaced = re.sub(r"([A-Z]+)([A-Z][a-z])", r"\1-\2", name)
    spaced = re.sub(r"([a-z0-9])([A-Z])", r"\1-\2", spaced)
    return spaced.lower()


def _package_leaf(package: str) -> str:
    """The package segment that names the surface: ``ibex.auth.v1`` -> ``auth``."""
    segments = [segment for segment in package.split(".") if segment]
    if len(segments) > 1 and segments[-1] == PROTO_VERSION_SEGMENT:
        segments.pop()
    return segments[-1] if segments else ""


def grpc_contract_id(method_key: str) -> str:
    """Derive the contract ID for a fully-qualified rpc name, or ``""`` when malformed."""
    segments = method_key.split(".")
    if len(segments) < 3:
        return ""
    leaf = _package_leaf(".".join(segments[:-2]))
    if not leaf:
        return ""
    return f"grpc.{leaf}.{_kebab(segments[-1])}.v1"


def mcp_contract_id(server: str, tool: str) -> str:
    """Derive the contract ID for a published MCP tool, or ``""`` when malformed."""
    leaf = server.removeprefix(MCP_SERVER_PREFIX) or server
    tool_leaf = tool.replace(".", "-").replace("_", "-").lower()
    if not leaf or not tool_leaf:
        return ""
    return f"mcp.{leaf}.{tool_leaf}.v1"


def _is_valid_contract_id(candidate: str) -> bool:
    """True when the ID matches the documented grammar (the document extractor's rule)."""
    return bool(candidate) and documented_contract_ids(candidate) == {candidate}


def grpc_method_parts(key: str) -> tuple[str, str] | None:
    """Split a ``grpc_methods`` key into ``(service, rpc)``, or ``None`` when malformed."""
    segments = key.split(".")
    if len(segments) < 3:
        return None
    return ".".join(segments[:-1]), segments[-1]


def mcp_tool_parts(key: str) -> tuple[str, str] | None:
    """Split a ``mcp_tools`` key into ``(server, tool)``, or ``None`` when malformed."""
    server, separator, tool = key.partition(MCP_KEY_SEPARATOR)
    if not separator or not server or not tool or MCP_KEY_SEPARATOR in tool:
        return None
    return server, tool


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


def _proto_text(source: Path) -> str:
    """Read a proto file with comments removed, so a commented-out block is not a contract."""
    text = source.read_text(encoding="utf-8")
    without_blocks = PROTO_BLOCK_COMMENT.sub("", text)
    return PROTO_LINE_COMMENT.sub("", without_blocks)


def _service_bodies(text: str) -> list[tuple[str, str]]:
    """Every ``service`` name with the text inside its braces (brace-matched)."""
    bodies: list[tuple[str, str]] = []
    for match in PROTO_SERVICE_PATTERN.finditer(text):
        start = match.end()
        depth = 1
        index = start
        while index < len(text) and depth:
            if text[index] == "{":
                depth += 1
            elif text[index] == "}":
                depth -= 1
            index += 1
        bodies.append((match.group(1), text[start : index - 1]))
    return bodies


def proto_services(proto_root: Path) -> dict[str, Path]:
    """Map fully-qualified protobuf service name to its source file."""
    services: dict[str, Path] = {}
    if not proto_root.is_dir():
        return services
    for source in sorted(proto_root.rglob("*.proto")):
        text = _proto_text(source)
        package_match = PROTO_PACKAGE_PATTERN.search(text)
        package = package_match.group(1) if package_match else ""
        for name, _body in _service_bodies(text):
            services[f"{package}.{name}" if package else name] = source
    return services


def proto_rpc_methods(proto_root: Path) -> dict[str, Path]:
    """Map a fully-qualified rpc name to the proto file that declares it."""
    methods: dict[str, Path] = {}
    if not proto_root.is_dir():
        return methods
    for source in sorted(proto_root.rglob("*.proto")):
        text = _proto_text(source)
        package_match = PROTO_PACKAGE_PATTERN.search(text)
        package = package_match.group(1) if package_match else ""
        for name, body in _service_bodies(text):
            service = f"{package}.{name}" if package else name
            for rpc in PROTO_RPC_PATTERN.findall(body):
                methods[f"{service}.{rpc}"] = source
    return methods


def _row_shape_failures(
    row: dict[str, object], label: str, fields: tuple[str, ...] = REQUIRED_FIELDS
) -> list[str]:
    """Field rules: every required field present, no unknown field, none empty."""
    failures: list[str] = []
    missing = [field for field in fields if field not in row]
    unknown = sorted(set(row) - set(fields))
    if missing:
        failures.append(f"missing-field: {label} lacks {', '.join(missing)}")
    if unknown:
        failures.append(f"unknown-field: {label} has {', '.join(unknown)}")
    empty = [field for field in fields if isinstance(row.get(field), str) and not row[field]]
    if empty:
        failures.append(f"empty-field: {label} has empty {', '.join(empty)}")
    return failures


def _row_enum_failures(
    row: dict[str, object], key: str, *, check_stability: bool = True
) -> list[str]:
    """The closed vocabularies a row must draw from."""
    failures: list[str] = []
    stability = row.get("stability")
    if check_stability and stability not in STABILITIES:
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


def _grpc_block(registry: dict[str, object]) -> dict[str, object] | None:
    out_of_scope = registry.get("out_of_scope")
    if not isinstance(out_of_scope, dict):
        return None
    grpc = out_of_scope.get("grpc")
    return grpc if isinstance(grpc, dict) else None


def _declared_out_services(registry: dict[str, object]) -> frozenset[str]:
    grpc = _grpc_block(registry)
    declared = grpc.get("declared_out") if grpc is not None else None
    if not isinstance(declared, list):
        return frozenset()
    return frozenset(str(name) for name in declared if _non_empty_str(name))


def _registered_service_names(registry: dict[str, object]) -> set[str]:
    grpc = _grpc_block(registry)
    registered = grpc.get("registered_services") if grpc is not None else None
    if not isinstance(registered, list):
        return set()
    names: set[str] = set()
    for item in registered:
        name = item.get("service") if isinstance(item, dict) else None
        if _non_empty_str(name):
            names.add(str(name))
    return names


def _grpc_method_row_failures(row: object, index: int, context: _CheckContext) -> list[str]:
    """One ``grpc_methods`` row: shape, enums, scaffold, evidence, derived contract ID."""
    label = f"grpc_methods[{index}]"
    if not isinstance(row, dict):
        return [f"invalid-row: {label} is not a JSON object"]
    key = _row_key(row)
    if key:
        label = key
    failures = _row_shape_failures(row, label, GRPC_METHOD_FIELDS)
    if not key:
        return failures + [f'invalid-key: {label} needs a non-empty "key"']
    if grpc_method_parts(key) is None:
        return failures + [f'invalid-key: {key} must be "<package>.<Service>.<Rpc>"']
    failures.extend(_row_enum_failures(row, key))
    failures.extend(_row_scaffold_failures(row, key))
    failures.extend(_row_evidence_failures(row, key, context))
    failures.extend(_grpc_method_contract_failures(row, key))
    return failures


def _grpc_method_contract_failures(row: dict[str, object], key: str) -> list[str]:
    expected = grpc_contract_id(key)
    if not _is_valid_contract_id(expected):
        return [f"invalid-contract-id: {key} derives {expected!r}, which is not a contract ID"]
    contract_id = row.get("contract_id")
    if contract_id == expected:
        return []
    return [
        (
            f"contract-id-mismatch: {key} declares {contract_id!r}; "
            f"the documented derivation gives {expected!r}"
        )
    ]


def _rpc_coverage_failures(
    registered_keys: set[str], declared_out: frozenset[str], context: _CheckContext
) -> list[str]:
    """Every declared rpc has a row, and every row still names a declared rpc."""
    failures: list[str] = []
    for key, source in context.rpcs.items():
        parts = grpc_method_parts(key)
        if parts is not None and parts[0] in declared_out:
            continue
        if key in registered_keys:
            continue
        failures.append(
            f"missing-registration: rpc {key} is declared in {_display_path(source)} but has no "
            f"grpc_methods row (contract_id {grpc_contract_id(key)!r})"
        )
    for key in sorted(registered_keys):
        if key in context.rpcs:
            continue
        failures.append(
            f"stale-registration: rpc {key} is registered but no such rpc exists under "
            "packages/proto/proto; remove the row"
        )
    return failures


def _service_cross_failures(
    registered_keys: set[str], registry: dict[str, object], context: _CheckContext
) -> list[str]:
    """The service index and the method rows must describe the same set of services."""
    grpc = _grpc_block(registry)
    if grpc is None:
        return []
    if not isinstance(grpc.get("registered_services"), list) or not isinstance(
        grpc.get("declared_out"), list
    ):
        # The malformed array has its own failure; a cross-check against a missing
        # index would only add noise.
        return []
    declared_out = _declared_out_services(registry)
    registered = _registered_service_names(registry)
    method_services = {
        parts[0] for key in registered_keys if (parts := grpc_method_parts(key)) is not None
    }
    failures: list[str] = []
    for service in sorted(method_services - registered - declared_out):
        failures.append(
            f"unregistered-service: {service} has grpc_methods rows but no "
            "out_of_scope.grpc.registered_services row"
        )
    for service in sorted(registered - method_services):
        if service in declared_out or service not in context.services:
            continue
        failures.append(
            f"method-less-service: {service} is registered but has no grpc_methods row; register "
            "its rpcs or move it to out_of_scope.grpc.declared_out"
        )
    for service in sorted((registered | method_services) & declared_out):
        failures.append(
            f"declared-out-conflict: {service} is listed in out_of_scope.grpc.declared_out but is "
            "also registered or carries grpc_methods rows"
        )
    return failures


def _grpc_method_failures(registry: dict[str, object], context: _CheckContext) -> list[str]:
    rows = registry.get("grpc_methods")
    if not isinstance(rows, list):
        return []
    failures: list[str] = []
    for index, row in enumerate(rows):
        failures.extend(_grpc_method_row_failures(row, index, context))
    failures.extend(_unsorted_failures(rows, "grpc_methods"))
    failures.extend(_duplicate_key_failures(rows, "grpc_methods"))
    registered_keys = {key for row in rows if (key := _row_key(row))}
    failures.extend(
        _rpc_coverage_failures(registered_keys, _declared_out_services(registry), context)
    )
    failures.extend(_service_cross_failures(registered_keys, registry, context))
    return failures


def load_mcp_surfaces(
    records: tuple[tuple[str, Path], ...],
) -> tuple[dict[str, tuple[Path, frozenset[str]]], list[str]]:
    """Read each committed descriptor record into ``server -> (path, tool names)``."""
    surfaces: dict[str, tuple[Path, frozenset[str]]] = {}
    failures: list[str] = []
    for server, path in records:
        payload, read_failures = _read_json(path, "mcp-record")
        if read_failures:
            failures.extend(read_failures)
            continue
        if not isinstance(payload, dict):
            failures.append(f"invalid-mcp-record: {path} must be a JSON object")
            continue
        tools = payload.get("tools")
        if not isinstance(tools, list):
            failures.append(f'missing-field: {path} needs a "tools" array')
            continue
        names: set[str] = set()
        for index, item in enumerate(tools):
            name = item.get("name") if isinstance(item, dict) else None
            if not _non_empty_str(name):
                failures.append(
                    f'invalid-mcp-record: {path} tools[{index}] needs a non-empty "name"'
                )
                continue
            names.add(str(name))
        surfaces[server] = (path, frozenset(names))
    return surfaces, failures


def _mcp_tool_row_failures(row: object, index: int, context: _CheckContext) -> list[str]:
    """One ``mcp_tools`` row: shape, status, scaffold, evidence, server, derived contract ID."""
    label = f"mcp_tools[{index}]"
    if not isinstance(row, dict):
        return [f"invalid-row: {label} is not a JSON object"]
    key = _row_key(row)
    if key:
        label = key
    failures = _row_shape_failures(row, label, MCP_TOOL_FIELDS)
    if not key:
        return failures + [f'invalid-key: {label} needs a non-empty "key"']
    parts = mcp_tool_parts(key)
    if parts is None:
        return failures + [f'invalid-key: {key} must be "<server>/<tool>"']
    failures.extend(_row_enum_failures(row, key, check_stability=False))
    failures.extend(_row_scaffold_failures(row, key))
    failures.extend(_row_evidence_failures(row, key, context))
    failures.extend(_mcp_tool_contract_failures(row, key, parts))
    return failures


def _mcp_tool_contract_failures(
    row: dict[str, object], key: str, parts: tuple[str, str]
) -> list[str]:
    server, tool = parts
    failures: list[str] = []
    if row.get("server") != server:
        failures.append(
            f"server-mismatch: {key} declares server {row.get('server')!r}; its key names {server!r}"
        )
    expected = mcp_contract_id(server, tool)
    if not _is_valid_contract_id(expected):
        failures.append(
            f"invalid-contract-id: {key} derives {expected!r}, which is not a contract ID"
        )
        return failures
    contract_id = row.get("contract_id")
    if contract_id != expected:
        failures.append(
            f"contract-id-mismatch: {key} declares {contract_id!r}; "
            f"the documented derivation gives {expected!r}"
        )
    return failures


def _mcp_registered_pairs(rows: list[object]) -> set[tuple[str, str]]:
    pairs: set[tuple[str, str]] = set()
    for row in rows:
        key = _row_key(row)
        parts = mcp_tool_parts(key) if key else None
        if parts is not None:
            pairs.add(parts)
    return pairs


def _mcp_coverage_failures(registered: set[tuple[str, str]], context: _CheckContext) -> list[str]:
    """Every recorded tool has a row, and every row still names a recorded tool."""
    failures: list[str] = []
    recorded = {
        (server, tool) for server, (_path, tools) in context.mcp_surfaces.items() for tool in tools
    }
    for server, tool in sorted(recorded - registered):
        path = context.mcp_surfaces[server][0]
        failures.append(
            f"missing-registration: mcp tool {server}/{tool} is recorded in "
            f"{_display_path(path)} but has no mcp_tools row "
            f"(contract_id {mcp_contract_id(server, tool)!r})"
        )
    for server, tool in sorted(registered - recorded):
        path = context.mcp_surfaces.get(server, (None, frozenset()))[0]
        where = _display_path(path) if path is not None else "any committed mcp_tools.json"
        failures.append(
            f"stale-registration: mcp tool {server}/{tool} is registered but is not recorded in "
            f"{where}"
        )
    return failures


def _mcp_tool_failures(registry: dict[str, object], context: _CheckContext) -> list[str]:
    rows = registry.get("mcp_tools")
    if not isinstance(rows, list):
        return []
    failures: list[str] = []
    for index, row in enumerate(rows):
        failures.extend(_mcp_tool_row_failures(row, index, context))
    failures.extend(_unsorted_failures(rows, "mcp_tools"))
    failures.extend(_duplicate_key_failures(rows, "mcp_tools"))
    failures.extend(_mcp_coverage_failures(_mcp_registered_pairs(rows), context))
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


def _unsorted_failures(rows: list[object], label: str = "routes") -> list[str]:
    """Report the first row that is out of order, naming what it is and what belongs there."""
    keys = [str(row.get("key", "")) for row in rows if isinstance(row, dict)]
    for index, expected in enumerate(sorted(keys)):
        if keys[index] != expected:
            return [
                (
                    f"unsorted-registry: {label}[{index}] is {keys[index]!r}; "
                    f"expected {expected!r} (rows are sorted by key)"
                )
            ]
    return []


def _duplicate_key_failures(rows: list[object], label: str) -> list[str]:
    """One row per key, so a malformed earlier row cannot hide behind a later one."""
    seen: dict[str, int] = {}
    failures: list[str] = []
    for index, row in enumerate(rows):
        key = _row_key(row)
        if key is None:
            continue
        if key in seen:
            failures.append(
                f"duplicate-key: {key} appears at {label}[{seen[key]}] and {label}[{index}]"
            )
        else:
            seen[key] = index
    return failures


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
    grpc_methods = registry.get("grpc_methods")
    if not isinstance(grpc_methods, list):
        return sorted(failures + ['missing-field: registry needs a "grpc_methods" array'])
    mcp_tools = registry.get("mcp_tools")
    if not isinstance(mcp_tools, list):
        return sorted(failures + ['missing-field: registry needs an "mcp_tools" array'])

    mcp_surfaces, mcp_failures = load_mcp_surfaces(paths.mcp_records)
    failures.extend(mcp_failures)

    context = _CheckContext(
        doc_ids=doc_ids,
        doc_label=doc_label,
        root=paths.root,
        services=proto_services(paths.proto_root),
        rpcs=proto_rpc_methods(paths.proto_root),
        mcp_surfaces=mcp_surfaces,
    )
    mounted = mounted_keys(inventory)
    rows_by_key, row_failures = _route_row_failures(routes, context)
    failures.extend(row_failures)
    failures.extend(_unsorted_failures(routes))
    failures.extend(_duplicate_contract_failures([*routes, *grpc_methods, *mcp_tools]))
    failures.extend(_coverage_failures(mounted, rows_by_key))
    failures.extend(_out_of_scope_failures(registry, context))
    failures.extend(_grpc_method_failures(registry, context))
    failures.extend(_mcp_tool_failures(registry, context))
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
            "reason": "gRPC request/response shapes are governed by buf-breaking (W5.1) and P0-12; this registry accounts for each proto service and each rpc method, not its message shapes.",
            "tracked_by": "P0-12",
            "registered_services": [],
            "declared_out": [],
        },
        "mcp_tools": {
            "reason": "MCP tool names are registered in the top-level mcp_tools array; their schemas are versioned descriptors checked by the descriptor diff (W5.5).",
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
    registry.setdefault("grpc_methods", [])
    registry.setdefault("mcp_tools", [])
    registry.setdefault("out_of_scope", _default_out_of_scope())
    paths.registry.parent.mkdir(parents=True, exist_ok=True)
    _write_registry(paths.registry, registry)
    return len(added), []


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Check that every mounted REST route, every declared gRPC rpc, and every recorded MCP "
            "tool is registered, with a derived contract ID (REST IDs must also appear in the "
            "contract document)."
        ),
        epilog=(
            '--write scaffolds missing keys only, always with owner "UNASSIGNED", stability '
            '"internal", and status "unregistered", so --check still fails until a human sets the '
            "real owner, reviews stability, records status, and cites existing evidence. --write "
            "never edits the contract document. It scaffolds REST routes only: a grpc_methods or "
            "mcp_tools row carries the same human decisions and is added by hand."
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
    print(
        'note: status "shipped" means declared, mounted, or recorded in this tree, not accepted '
        "or supported"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
