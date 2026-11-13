"""The cross-surface rules: a REST or gRPC entry against the route registry, an MCP
entry against its server's committed descriptor.

These are the only rules that read a second document, so they live apart from the
per-entry value rules in ``deprecations_fields``: an entry's own shape is judged
there, and whether the contract or tool it names exists, and with which class, is
judged here.

A completed MCP tool removal has one definition, and both checks that decide whether a
removal is allowed use it: the tool *and* its entry are removed in the same change, at
the sunset date. This module is the side that refuses the half-removal: an entry whose
``tool`` the descriptor no longer records is a phantom, whatever its window says
(``unknown-tool``). ``packages/mcp_tool_descriptors`` reads the same definition from
the other side: a removal is authorised by the entry that covered the tool at the base
ref, which is exactly the entry this check stops requiring once the tool is gone. A
tool that never existed is not a completed removal in either place: it fails
``unknown-tool`` here, and it was not recorded at the base ref, so no entry there can
cover it.

Standard library only; the record and the REST registry are loaded by
``deprecations_model``. The ``grpc_methods`` rows live in that same registry, so the
context carries the path it was loaded from; ``_grpc_stabilities`` reads them from
that path, never from the display label a failure prints.
"""

from __future__ import annotations

import json

from deprecations_model import MCP_SERVERS, CheckContext, display_path, non_empty_str


def _unknown_contract_failure(contract_id: object, label: str, context: CheckContext) -> str:
    return (
        f"unknown-contract: {label} deprecates {contract_id}, which has no row in "
        f"{context.rest_label}"
    )


def _contract_failures(
    entry: dict[str, object],
    label: str,
    context: CheckContext,
    stabilities: dict[str, str],
) -> list[str]:
    """Resolve one entry's ``contract_id`` and class against a registry surface's rows.

    REST and gRPC rows live in the same registry and carry the same two fields, so they
    share this rule; only the mapping the entry resolves against differs.
    """
    contract_id = entry.get("contract_id")
    if not non_empty_str(contract_id):
        return []
    stability = stabilities.get(str(contract_id))
    if stability is None:
        return [_unknown_contract_failure(contract_id, label, context)]
    if stability != entry.get("stability"):
        return [
            (
                f"stability-mismatch: {label} records {entry.get('stability')!r} but "
                f"{context.rest_label} records {stability!r} for {contract_id}"
            )
        ]
    return []


def _rest_failures(entry: dict[str, object], label: str, context: CheckContext) -> list[str]:
    return _contract_failures(entry, label, context, context.rest)


def _grpc_stabilities(context: CheckContext) -> dict[str, str]:
    """``contract_id -> stability`` for the registry's ``grpc_methods`` rows.

    The rows are read from the path the registry was loaded from, so a relative
    ``--rest-registry`` resolves against the caller's working directory, exactly as
    the initial load did. ``rest_label`` is a display string, not a path: rebuilding
    one from it would resolve against the repository root instead, and would read the
    wrong file (or none) whenever the run is started outside the repository.

    ``load_rest_registry`` has already failed the run on an unreadable or malformed
    registry, so only the rows themselves are read here.
    """
    try:
        payload = json.loads(context.rest_registry.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError, RecursionError):
        return {}
    rows = payload.get("grpc_methods") if isinstance(payload, dict) else None
    if not isinstance(rows, list):
        return {}
    return {
        str(row["contract_id"]): str(row.get("stability"))
        for row in rows
        if isinstance(row, dict) and non_empty_str(row.get("contract_id"))
    }


def _grpc_failures(entry: dict[str, object], label: str, context: CheckContext) -> list[str]:
    """A gRPC entry resolves against ``grpc_methods``, the same way a REST one does."""
    return _contract_failures(entry, label, context, _grpc_stabilities(context))


def _unknown_server_failures(label: str, server: object) -> list[str]:
    return [
        (f"unknown-server: {label} names server {server!r}; expected one of {sorted(MCP_SERVERS)}")
    ]


def _mcp_failures(entry: dict[str, object], label: str, context: CheckContext) -> list[str]:
    server = entry.get("server")
    if not non_empty_str(server) or str(server) not in MCP_SERVERS:
        return _unknown_server_failures(label, server)
    tool = entry.get("tool")
    if not non_empty_str(tool):
        return []
    tools = context.mcp[str(server)]
    stability = tools.get(str(tool))
    if stability is None:
        return [
            (
                f"unknown-tool: {label} deprecates tool {tool!r}, which is absent from "
                f"{display_path(context.mcp_paths[str(server)])}"
            )
        ]
    if stability != entry.get("stability"):
        return [
            (
                f"stability-mismatch: {label} records {entry.get('stability')!r} but "
                f"{display_path(context.mcp_paths[str(server)])} records {stability!r} for tool "
                f"{tool!r}"
            )
        ]
    return []


def registry_failures(entry: dict[str, object], label: str, context: CheckContext) -> list[str]:
    """The rules that resolve an entry against the registry its surface is recorded in."""
    surface = entry.get("surface")
    if surface == "rest":
        return _rest_failures(entry, label, context)
    if surface == "grpc":
        return _grpc_failures(entry, label, context)
    if surface == "mcp":
        return _mcp_failures(entry, label, context)
    return []
