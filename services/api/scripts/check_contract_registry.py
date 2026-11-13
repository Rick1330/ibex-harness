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

No network access, no third-party dependency, deterministic output. This module
keeps the CLI and the orchestration; the rules live beside it, split by surface::

    contract_registry_model.py          schema constants, paths, shared dataclasses
    contract_registry_derive.py         contract-ID derivation and key parsing
    contract_registry_proto.py          proto tree: services and rpc methods
    contract_registry_rows.py           row rules every surface shares
    contract_registry_rest.py           the inventory and the ``routes`` rows
    contract_registry_out_of_scope.py   the ``out_of_scope`` service index
    contract_registry_grpc.py           ``grpc_methods`` rows and cross-checks
    contract_registry_mcp.py            descriptor records and ``mcp_tools`` rows
    contract_registry_write.py          ``--write`` scaffolding, atomic write

The contract-ID grammar (candidate validation and document extraction) lives in
``contract_ids.py`` beside this script.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Final, cast

from contract_ids import documented_contract_ids
from contract_registry_grpc import grpc_method_failures
from contract_registry_mcp import load_mcp_surfaces, mcp_tool_failures
from contract_registry_model import (
    DEFAULT_PATHS,
    CheckContext,
    RegistryPaths,
    display_path,
    load_registry,
    schema_failures,
)
from contract_registry_out_of_scope import out_of_scope_failures
from contract_registry_proto import proto_rpc_methods, proto_services
from contract_registry_rest import (
    coverage_failures,
    load_inventory,
    mounted_keys,
    route_row_failures,
)
from contract_registry_rows import duplicate_contract_failures, unsorted_failures
from contract_registry_write import scaffold

REGISTRY_ARRAYS: Final = ("routes", "grpc_methods", "mcp_tools")
# The wording is part of the checked contract: the unit tests assert these exact
# strings, so each array keeps the message it has always produced.
MISSING_ARRAY_MESSAGES: Final = {
    "routes": 'missing-field: registry needs a "routes" array',
    "grpc_methods": 'missing-field: registry needs a "grpc_methods" array',
    "mcp_tools": 'missing-field: registry needs an "mcp_tools" array',
}


def _missing_array_failure(registry: dict[str, object]) -> str:
    """Name the first required array that is absent, or ``""`` when all three are arrays."""
    for field in REGISTRY_ARRAYS:
        if not isinstance(registry.get(field), list):
            return MISSING_ARRAY_MESSAGES[field]
    return ""


def _registry_arrays(
    registry: dict[str, object],
) -> tuple[list[object], list[object], list[object]]:
    """The three required arrays; call only after ``_missing_array_failure`` returned ``""``."""
    return (
        cast(list[object], registry["routes"]),
        cast(list[object], registry["grpc_methods"]),
        cast(list[object], registry["mcp_tools"]),
    )


def _load_inputs(
    paths: RegistryPaths,
) -> tuple[list[dict[str, object]], dict[str, object], list[str]]:
    """Read the inventory and the registry; a non-empty failure list is fatal."""
    inventory, inventory_failures = load_inventory(paths.inventory)
    registry, registry_failures = load_registry(paths.registry)
    return inventory, registry, inventory_failures + registry_failures


def _document_ids(paths: RegistryPaths) -> tuple[frozenset[str], str]:
    """The contract IDs the document carries, and the label failures name it by."""
    doc_text = paths.doc.read_text(encoding="utf-8") if paths.doc.exists() else ""
    return documented_contract_ids(doc_text), display_path(paths.doc)


def _check_context(
    paths: RegistryPaths,
    mcp_surfaces: dict[str, tuple[Path, frozenset[str]]],
    document: tuple[frozenset[str], str],
) -> CheckContext:
    """Resolve the proto and descriptor surfaces once per run."""
    doc_ids, doc_label = document
    return CheckContext(
        doc_ids=doc_ids,
        doc_label=doc_label,
        root=paths.root,
        services=proto_services(paths.proto_root),
        rpcs=proto_rpc_methods(paths.proto_root),
        mcp_surfaces=mcp_surfaces,
    )


def check(paths: RegistryPaths = DEFAULT_PATHS) -> list[str]:
    """Return every failure; an empty list means the registry is complete."""
    inventory, registry, load_failures = _load_inputs(paths)
    if load_failures:
        return sorted(load_failures)
    schema = schema_failures(registry)
    document = _document_ids(paths)
    missing = _missing_array_failure(registry)
    if missing:
        return sorted([*schema, missing])
    routes, grpc_methods, mcp_tools = _registry_arrays(registry)
    mcp_surfaces, mcp_failures = load_mcp_surfaces(paths.mcp_records)
    context = _check_context(paths, mcp_surfaces, document)
    rows_by_key, row_failures = route_row_failures(routes, context)
    failures = [
        *schema,
        *mcp_failures,
        *row_failures,
        *unsorted_failures(routes),
        *duplicate_contract_failures([*routes, *grpc_methods, *mcp_tools]),
        *coverage_failures(mounted_keys(inventory), rows_by_key),
        *out_of_scope_failures(registry, context),
        *grpc_method_failures(registry, context),
        *mcp_tool_failures(registry, context),
    ]
    return sorted(failures)


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
