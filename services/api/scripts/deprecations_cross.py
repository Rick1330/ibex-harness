"""The cross-surface rules: a REST entry against the route registry, an MCP entry
against its server's committed descriptor.

These are the only rules that read a second document, so they live apart from the
per-entry value rules in ``deprecations_fields``: an entry's own shape is judged
there, and whether the contract or tool it names exists, and with which class, is
judged here. A ``grpc`` entry resolves against no registry yet, so it has no rule
in this module.

Standard library only; the two registries are loaded by ``deprecations_model``.
"""

from __future__ import annotations

from deprecations_model import MCP_SERVERS, CheckContext, display_path, non_empty_str


def _rest_failures(entry: dict[str, object], label: str, context: CheckContext) -> list[str]:
    contract_id = entry.get("contract_id")
    if not non_empty_str(contract_id):
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
    if surface == "mcp":
        return _mcp_failures(entry, label, context)
    return []
