"""The ``grpc_methods`` rows and their two cross-checks.

A row names a fully-qualified rpc the proto tree declares, carries the derived
contract ID, and is cross-checked against the proto tree in both directions:
every declared rpc has a row, and every row still names a declared rpc. The
service index and the method rows are then cross-checked, so a service cannot
carry rows without a registration, be registered without rows, or be both
registered and declared out.

Standard library only; no I/O beyond the evidence paths the shared row rules read.
"""

from __future__ import annotations

from pathlib import Path

from contract_registry_derive import grpc_contract_id, grpc_method_parts, is_valid_contract_id
from contract_registry_model import GRPC_METHOD_FIELDS, CheckContext, display_path
from contract_registry_out_of_scope import (
    declared_out_services,
    grpc_block,
    registered_service_names,
)
from contract_registry_rows import (
    duplicate_key_failures,
    row_enum_failures,
    row_evidence_failures,
    row_key,
    row_scaffold_failures,
    row_shape_failures,
    unsorted_failures,
)


def grpc_method_contract_failures(row: dict[str, object], key: str) -> list[str]:
    expected = grpc_contract_id(key)
    if not is_valid_contract_id(expected):
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


def grpc_method_row_failures(row: object, index: int, context: CheckContext) -> list[str]:
    """One ``grpc_methods`` row: shape, enums, scaffold, evidence, derived contract ID."""
    label = f"grpc_methods[{index}]"
    if not isinstance(row, dict):
        return [f"invalid-row: {label} is not a JSON object"]
    key = row_key(row)
    if key:
        label = key
    failures = row_shape_failures(row, label, GRPC_METHOD_FIELDS)
    if not key:
        return failures + [f'invalid-key: {label} needs a non-empty "key"']
    if grpc_method_parts(key) is None:
        return failures + [f'invalid-key: {key} must be "<package>.<Service>.<Rpc>"']
    failures.extend(row_enum_failures(row, key))
    failures.extend(row_scaffold_failures(row, key))
    failures.extend(row_evidence_failures(row, key, context))
    failures.extend(grpc_method_contract_failures(row, key))
    return failures


def _rpc_needs_row(key: str, registered_keys: set[str], declared_out: frozenset[str]) -> bool:
    """A declared-out service is exempt; a registered key already has its row."""
    parts = grpc_method_parts(key)
    if parts is not None and parts[0] in declared_out:
        return False
    return key not in registered_keys


def _missing_rpc_message(key: str, source: Path) -> str:
    return (
        f"missing-registration: rpc {key} is declared in {display_path(source)} but has no "
        f"grpc_methods row (contract_id {grpc_contract_id(key)!r})"
    )


def _missing_rpc_failures(
    registered_keys: set[str], declared_out: frozenset[str], context: CheckContext
) -> list[str]:
    return [
        _missing_rpc_message(key, source)
        for key, source in context.rpcs.items()
        if _rpc_needs_row(key, registered_keys, declared_out)
    ]


def _stale_rpc_failures(registered_keys: set[str], context: CheckContext) -> list[str]:
    return [
        f"stale-registration: rpc {key} is registered but no such rpc exists under "
        "packages/proto/proto; remove the row"
        for key in sorted(registered_keys)
        if key not in context.rpcs
    ]


def rpc_coverage_failures(
    registered_keys: set[str], declared_out: frozenset[str], context: CheckContext
) -> list[str]:
    """Every declared rpc has a row, and every row still names a declared rpc."""
    failures = _missing_rpc_failures(registered_keys, declared_out, context)
    failures.extend(_stale_rpc_failures(registered_keys, context))
    return failures


def _well_formed_index(grpc: dict[str, object]) -> bool:
    return isinstance(grpc.get("registered_services"), list) and isinstance(
        grpc.get("declared_out"), list
    )


def _service_index(registry: dict[str, object]) -> tuple[frozenset[str], set[str]] | None:
    """``(declared_out, registered)``, or ``None`` when the index is malformed.

    The malformed array has its own failure; a cross-check against a missing index
    would only add noise.
    """
    grpc = grpc_block(registry)
    if grpc is None:
        return None
    if not _well_formed_index(grpc):
        return None
    return declared_out_services(registry), registered_service_names(registry)


def _method_services(registered_keys: set[str]) -> set[str]:
    services: set[str] = set()
    for key in registered_keys:
        parts = grpc_method_parts(key)
        if parts is not None:
            services.add(parts[0])
    return services


def _unregistered_service_failures(
    method_services: set[str], registered: set[str], declared_out: frozenset[str]
) -> list[str]:
    return [
        f"unregistered-service: {service} has grpc_methods rows but no "
        "out_of_scope.grpc.registered_services row"
        for service in sorted(method_services - registered - declared_out)
    ]


def _needs_method_rows(
    service: str, declared_out: frozenset[str], services: dict[str, Path]
) -> bool:
    """A declared-out or unknown service has no method rows to check."""
    if service in declared_out:
        return False
    return service in services


def _method_less_service_failures(
    registered: set[str],
    method_services: set[str],
    declared_out: frozenset[str],
    context: CheckContext,
) -> list[str]:
    return [
        f"method-less-service: {service} is registered but has no grpc_methods row; register "
        "its rpcs or move it to out_of_scope.grpc.declared_out"
        for service in sorted(registered - method_services)
        if _needs_method_rows(service, declared_out, context.services)
    ]


def _declared_out_conflict_failures(
    registered: set[str], method_services: set[str], declared_out: frozenset[str]
) -> list[str]:
    return [
        f"declared-out-conflict: {service} is listed in out_of_scope.grpc.declared_out but is "
        "also registered or carries grpc_methods rows"
        for service in sorted((registered | method_services) & declared_out)
    ]


def service_cross_failures(
    registered_keys: set[str], registry: dict[str, object], context: CheckContext
) -> list[str]:
    """The service index and the method rows must describe the same set of services."""
    index = _service_index(registry)
    if index is None:
        return []
    declared_out, registered = index
    method_services = _method_services(registered_keys)
    failures = _unregistered_service_failures(method_services, registered, declared_out)
    failures.extend(
        _method_less_service_failures(registered, method_services, declared_out, context)
    )
    failures.extend(_declared_out_conflict_failures(registered, method_services, declared_out))
    return failures


def grpc_method_failures(registry: dict[str, object], context: CheckContext) -> list[str]:
    rows = registry.get("grpc_methods")
    if not isinstance(rows, list):
        return []
    failures: list[str] = []
    for index, row in enumerate(rows):
        failures.extend(grpc_method_row_failures(row, index, context))
    failures.extend(unsorted_failures(rows, "grpc_methods"))
    failures.extend(duplicate_key_failures(rows, "grpc_methods"))
    registered_keys = {key for row in rows if (key := row_key(row))}
    failures.extend(
        rpc_coverage_failures(registered_keys, declared_out_services(registry), context)
    )
    failures.extend(service_cross_failures(registered_keys, registry, context))
    return failures
