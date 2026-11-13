"""The MCP surface: committed descriptor records and the ``mcp_tools`` rows.

Each MCP service commits an ``mcp_tools.json`` record of the tools it publishes.
A tool recorded there must have a row, a row must still name a recorded tool,
and the row's ``server`` field must agree with its ``<server>/<tool>`` key, so a
tool cannot be attached to the wrong surface.

Standard library only; reads the committed descriptor records.
"""

from __future__ import annotations

from pathlib import Path

from contract_registry_derive import is_valid_contract_id, mcp_contract_id, mcp_tool_parts
from contract_registry_model import MCP_TOOL_FIELDS, CheckContext, display_path, read_json
from contract_registry_rows import (
    duplicate_key_failures,
    row_enum_failures,
    row_evidence_failures,
    row_key,
    row_scaffold_failures,
    row_shape_failures,
    unsorted_failures,
)


def _tool_name(item: object) -> str | None:
    name = item.get("name") if isinstance(item, dict) else None
    if not isinstance(name, str) or not name:
        return None
    return name


def _record_tool_names(path: Path, tools: list[object]) -> tuple[frozenset[str], list[str]]:
    names: set[str] = set()
    failures: list[str] = []
    for index, item in enumerate(tools):
        name = _tool_name(item)
        if name is None:
            failures.append(f'invalid-mcp-record: {path} tools[{index}] needs a non-empty "name"')
            continue
        names.add(name)
    return frozenset(names), failures


def _record_tools(path: Path, payload: object) -> tuple[list[object], list[str]]:
    """The record's ``tools`` array, or the failure that makes the record unusable."""
    if not isinstance(payload, dict):
        return [], [f"invalid-mcp-record: {path} must be a JSON object"]
    tools = payload.get("tools")
    if not isinstance(tools, list):
        return [], [f'missing-field: {path} needs a "tools" array']
    return tools, []


def load_mcp_surfaces(
    records: tuple[tuple[str, Path], ...],
) -> tuple[dict[str, tuple[Path, frozenset[str]]], list[str]]:
    """Read each committed descriptor record into ``server -> (path, tool names)``."""
    surfaces: dict[str, tuple[Path, frozenset[str]]] = {}
    failures: list[str] = []
    for server, path in records:
        payload, read_failures = read_json(path, "mcp-record")
        if read_failures:
            failures.extend(read_failures)
            continue
        tools, shape_failures = _record_tools(path, payload)
        if shape_failures:
            failures.extend(shape_failures)
            continue
        names, name_failures = _record_tool_names(path, tools)
        failures.extend(name_failures)
        surfaces[server] = (path, names)
    return surfaces, failures


def mcp_tool_contract_failures(
    row: dict[str, object], key: str, parts: tuple[str, str]
) -> list[str]:
    server, tool = parts
    failures: list[str] = []
    if row.get("server") != server:
        failures.append(
            f"server-mismatch: {key} declares server {row.get('server')!r}; its key names {server!r}"
        )
    expected = mcp_contract_id(server, tool)
    if not is_valid_contract_id(expected):
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


def mcp_tool_row_failures(row: object, index: int, context: CheckContext) -> list[str]:
    """One ``mcp_tools`` row: shape, status, scaffold, evidence, server, derived contract ID."""
    label = f"mcp_tools[{index}]"
    if not isinstance(row, dict):
        return [f"invalid-row: {label} is not a JSON object"]
    key = row_key(row)
    if key:
        label = key
    failures = row_shape_failures(row, label, MCP_TOOL_FIELDS)
    if not key:
        return failures + [f'invalid-key: {label} needs a non-empty "key"']
    parts = mcp_tool_parts(key)
    if parts is None:
        return failures + [f'invalid-key: {key} must be "<server>/<tool>"']
    failures.extend(row_enum_failures(row, key, check_stability=False))
    failures.extend(row_scaffold_failures(row, key))
    failures.extend(row_evidence_failures(row, key, context))
    failures.extend(mcp_tool_contract_failures(row, key, parts))
    return failures


def mcp_registered_pairs(rows: list[object]) -> set[tuple[str, str]]:
    pairs: set[tuple[str, str]] = set()
    for row in rows:
        key = row_key(row)
        parts = mcp_tool_parts(key) if key else None
        if parts is not None:
            pairs.add(parts)
    return pairs


def _recorded_pairs(context: CheckContext) -> set[tuple[str, str]]:
    return {
        (server, tool) for server, (_path, tools) in context.mcp_surfaces.items() for tool in tools
    }


def _missing_tool_failures(missing: set[tuple[str, str]], context: CheckContext) -> list[str]:
    return [
        (
            f"missing-registration: mcp tool {server}/{tool} is recorded in "
            f"{display_path(context.mcp_surfaces[server][0])} but has no mcp_tools row "
            f"(contract_id {mcp_contract_id(server, tool)!r})"
        )
        for server, tool in sorted(missing)
    ]


def _stale_tool_message(server: str, tool: str, context: CheckContext) -> str:
    path = context.mcp_surfaces.get(server, (None, frozenset()))[0]
    where = display_path(path) if path is not None else "any committed mcp_tools.json"
    # nosemgrep: semgrep.rules.ibex-no-raw-sql-format -- diagnostic message, not a query
    return (
        f"stale-registration: mcp tool {server}/{tool} is registered but is not recorded in {where}"
    )


def _stale_tool_failures(stale: set[tuple[str, str]], context: CheckContext) -> list[str]:
    return [_stale_tool_message(server, tool, context) for server, tool in sorted(stale)]


def mcp_coverage_failures(registered: set[tuple[str, str]], context: CheckContext) -> list[str]:
    """Every recorded tool has a row, and every row still names a recorded tool."""
    recorded = _recorded_pairs(context)
    failures = _missing_tool_failures(recorded - registered, context)
    failures.extend(_stale_tool_failures(registered - recorded, context))
    return failures


def mcp_tool_failures(registry: dict[str, object], context: CheckContext) -> list[str]:
    rows = registry.get("mcp_tools")
    if not isinstance(rows, list):
        return []
    failures: list[str] = []
    for index, row in enumerate(rows):
        failures.extend(mcp_tool_row_failures(row, index, context))
    failures.extend(unsorted_failures(rows, "mcp_tools"))
    failures.extend(duplicate_key_failures(rows, "mcp_tools"))
    failures.extend(mcp_coverage_failures(mcp_registered_pairs(rows), context))
    return failures
