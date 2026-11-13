"""``--write``: scaffold missing REST rows without laundering them into claims.

A scaffold records nothing a human decided. Every new row carries the
``UNASSIGNED`` owner sentinel, the conservative ``internal`` stability, the
``unregistered`` status, and the router source from the inventory as evidence,
so ``--check`` keeps failing until a human sets a real owner, reviews stability,
records status, and cites a file that exists. The registry is replaced
atomically, so an interrupted run cannot truncate it.

Standard library only; writes only the registry file it is given.
"""

from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path

from contract_registry_derive import derive_contract_id
from contract_registry_model import (
    DEFAULT_EVIDENCE,
    DEFAULT_PATHS,
    SCAFFOLD_OWNER,
    SCAFFOLD_STABILITY,
    SCHEMA,
    RegistryPaths,
    load_registry,
    route_key,
)
from contract_registry_rest import load_inventory


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


def write_registry(path: Path, registry: dict[str, object]) -> None:
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


def _row_scaffold_rows(row: dict[str, object], existing: set[str]) -> list[dict[str, str]]:
    path = str(row.get("path", ""))
    return [
        scaffold_row(str(method), path, row.get("source"))
        for method in row.get("methods", ())
        if route_key(str(method), path) not in existing
    ]


def missing_scaffold_rows(
    inventory: list[dict[str, object]], existing: set[str]
) -> list[dict[str, str]]:
    added: list[dict[str, str]] = []
    for row in inventory:
        added.extend(_row_scaffold_rows(row, existing))
    return added


def default_out_of_scope() -> dict[str, object]:
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


def _registry_rows(registry: dict[str, object]) -> list[dict[str, object]]:
    routes = registry.get("routes")
    if not isinstance(routes, list):
        return []
    return [row for row in routes if isinstance(row, dict)]


def _merge_scaffold(
    registry: dict[str, object],
    existing_rows: list[dict[str, object]],
    added: list[dict[str, str]],
) -> None:
    registry["routes"] = sorted([*existing_rows, *added], key=lambda row: str(row.get("key")))
    registry.setdefault("schema", SCHEMA)
    registry.setdefault("grpc_methods", [])
    registry.setdefault("mcp_tools", [])
    registry.setdefault("out_of_scope", default_out_of_scope())


def scaffold(paths: RegistryPaths = DEFAULT_PATHS) -> tuple[int, list[str]]:
    """Add unregistered rows for missing keys; return the count and any failures."""
    inventory, failures = load_inventory(paths.inventory)
    registry, registry_failures = load_registry(paths.registry)
    failures = failures + registry_failures
    if failures:
        return 0, sorted(failures)
    existing_rows = _registry_rows(registry)
    added = missing_scaffold_rows(inventory, {str(row.get("key")) for row in existing_rows})
    if not added:
        return 0, []
    _merge_scaffold(registry, existing_rows, added)
    paths.registry.parent.mkdir(parents=True, exist_ok=True)
    write_registry(paths.registry, registry)
    return len(added), []
