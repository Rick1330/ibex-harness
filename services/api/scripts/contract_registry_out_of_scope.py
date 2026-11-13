"""The ``out_of_scope`` block: what the registry declares outside method rows.

``out_of_scope.grpc`` is the service accounting point: every protobuf service is
either listed in ``registered_services`` with an owner, contract ID, and
documented ID, or named in ``declared_out``. Both surfaces must state a reason
and the owner item that tracks them. This module validates that block and the
accessors the gRPC method checks read it through.

Standard library only; no I/O.
"""

from __future__ import annotations

from pathlib import Path

from contract_registry_model import CheckContext, display_path, non_empty_str


def surface_entry_failures(out_of_scope: dict[str, object]) -> list[str]:
    """Every out-of-scope surface must state a reason and name its owner item."""
    failures: list[str] = []
    for surface in ("grpc", "mcp_tools"):
        failures.extend(entry_failures(surface, out_of_scope.get(surface)))
    return failures


def entry_failures(surface: str, entry: object) -> list[str]:
    if not isinstance(entry, dict):
        return [f"missing-field: out_of_scope.{surface} must be an object"]
    failures = entry_text_failures(surface, entry)
    if surface == "grpc":
        failures.extend(grpc_tracked_by_failures(entry.get("tracked_by")))
    return failures


def entry_text_failures(surface: str, entry: dict[str, object]) -> list[str]:
    failures: list[str] = []
    if not non_empty_str(entry.get("reason")):
        failures.append(f"empty-field: out_of_scope.{surface}.reason must state the reason")
    if not non_empty_str(entry.get("tracked_by")):
        failures.append(f"empty-field: out_of_scope.{surface}.tracked_by must name the owner item")
    return failures


def grpc_tracked_by_failures(tracked_by: object) -> list[str]:
    if tracked_by == "P0-12":
        return []
    return [f"unknown-enum: out_of_scope.grpc.tracked_by is {tracked_by!r}; expected 'P0-12'"]


def grpc_entry_failures(
    item: object, index: int, context: CheckContext
) -> tuple[str | None, list[str]]:
    """Validate one ``registered_services`` entry; return its service name and failures.

    ``None`` means the entry named no usable service, so the caller must not count
    it as registered.
    """
    label = f"out_of_scope.grpc.registered_services[{index}]"
    if not isinstance(item, dict):
        return None, [f"invalid-row: {label} is not a JSON object"]
    name = item.get("service")
    if not non_empty_str(name):
        return None, [f"empty-field: {label}.service must name a protobuf service"]
    return str(name), grpc_entry_field_failures(item, str(name), label, context)


def grpc_entry_field_failures(
    item: dict[str, object], name: str, label: str, context: CheckContext
) -> list[str]:
    failures = grpc_service_failures(name, context.services)
    failures.extend(grpc_contract_failures(item.get("contract_id"), name, label, context))
    if not non_empty_str(item.get("owner")):
        failures.append(f"empty-field: {label}.owner must name the owning service")
    return failures


def grpc_service_failures(name: str, services: dict[str, Path]) -> list[str]:
    if name in services:
        return []
    return [
        (
            f"stale-proto-registration: {name} is registered but no such service exists under "
            "packages/proto/proto"
        )
    ]


def grpc_contract_failures(
    contract_id: object, name: str, label: str, context: CheckContext
) -> list[str]:
    if not non_empty_str(contract_id):
        return [f"empty-field: {label}.contract_id must name a registered contract"]
    if contract_id in context.doc_ids:
        return []
    return [
        f"undocumented-contract: {contract_id} for {name} does not appear in {context.doc_label}"
    ]


def grpc_registration_failures(
    registered: list[object], context: CheckContext
) -> tuple[set[str], list[str]]:
    """Validate every registered gRPC service; return the usable names and failures."""
    names: set[str] = set()
    failures: list[str] = []
    for index, item in enumerate(registered):
        name, entry_failures = grpc_entry_failures(item, index, context)
        if name is not None:
            names.add(name)
        failures.extend(entry_failures)
    return names, failures


def _accounted_for(name: str, registered_names: set[str], declared_out: list[object]) -> bool:
    """A service is accounted for once it is registered or explicitly declared out."""
    if name in registered_names:
        return True
    return name in declared_out


def unaccounted_service_failures(
    services: dict[str, Path], registered_names: set[str], declared_out: list[object]
) -> list[str]:
    """Every proto service is either registered here or explicitly declared out."""
    return [
        (
            f"unaccounted-proto-service: {name} ({display_path(source)}) is "
            "neither registered in out_of_scope.grpc.registered_services nor listed in "
            "out_of_scope.grpc.declared_out"
        )
        for name, source in services.items()
        if not _accounted_for(name, registered_names, declared_out)
    ]


def grpc_failures(grpc: dict[str, object], context: CheckContext) -> list[str]:
    registered = grpc.get("registered_services")
    declared_out = grpc.get("declared_out")
    if not isinstance(registered, list):
        return ["missing-field: out_of_scope.grpc.registered_services must be an array"]
    if not isinstance(declared_out, list):
        return ["missing-field: out_of_scope.grpc.declared_out must be an array"]
    registered_names, failures = grpc_registration_failures(registered, context)
    failures.extend(unaccounted_service_failures(context.services, registered_names, declared_out))
    return failures


def out_of_scope_failures(registry: dict[str, object], context: CheckContext) -> list[str]:
    out_of_scope = registry.get("out_of_scope")
    if not isinstance(out_of_scope, dict):
        return ['missing-field: registry needs an "out_of_scope" object']
    failures = surface_entry_failures(out_of_scope)
    grpc = out_of_scope.get("grpc")
    if not isinstance(grpc, dict):
        return failures
    failures.extend(grpc_failures(grpc, context))
    return failures


def grpc_block(registry: dict[str, object]) -> dict[str, object] | None:
    out_of_scope = registry.get("out_of_scope")
    if not isinstance(out_of_scope, dict):
        return None
    grpc = out_of_scope.get("grpc")
    return grpc if isinstance(grpc, dict) else None


def declared_out_services(registry: dict[str, object]) -> frozenset[str]:
    grpc = grpc_block(registry)
    declared = grpc.get("declared_out") if grpc is not None else None
    if not isinstance(declared, list):
        return frozenset()
    return frozenset(str(name) for name in declared if non_empty_str(name))


def registered_service_names(registry: dict[str, object]) -> set[str]:
    grpc = grpc_block(registry)
    registered = grpc.get("registered_services") if grpc is not None else None
    if not isinstance(registered, list):
        return set()
    names: set[str] = set()
    for item in registered:
        name = item.get("service") if isinstance(item, dict) else None
        if non_empty_str(name):
            names.add(str(name))
    return names
