"""Unit tests for the MCP half of the contract registry check (P0-14 / W5.5).

``mcp_tools`` rows are checked against the committed ``mcp_tools.json`` records,
so these tests pin the derivation, the coverage in both directions (a recorded
tool needs a row, a row needs a recorded tool), the ``server`` field agreement,
and the failure that a missing or malformed record produces.

The REST and gRPC halves live in ``test_contract_registry.py`` and
``test_contract_registry_grpc.py``; the workspace builder they all share is in
``contract_registry_test_support.py``.
"""

from __future__ import annotations

from pathlib import Path
from types import ModuleType

import pytest

from tests.unit.contract_registry_test_support import (
    MCP_SERVER,
    MCP_TOOL_KEY,
    WorkspaceSpec,
    cli,
    derive,
    mcp_row,
    model,
    workspace,
)


@pytest.fixture(scope="module")
def registry_check() -> ModuleType:
    """The CLI module: ``check``, ``main``, and the committed paths."""
    return cli


def test_mcp_derivation_is_mechanical() -> None:
    assert derive.mcp_contract_id("ibex-mcp-operator", "budget.get") == "mcp.operator.budget-get.v1"
    assert (
        derive.mcp_contract_id("ibex-mcp-memory", "search_memory") == "mcp.memory.search-memory.v1"
    )


def test_recorded_tool_without_a_row_fails(tmp_path: Path, registry_check: ModuleType) -> None:
    paths = workspace(tmp_path, [("GET", "/v1/agents")], WorkspaceSpec(mcp_tools=[]))
    failures = registry_check.check(paths)
    assert any(
        failure.startswith(f"missing-registration: mcp tool {MCP_TOOL_KEY} ")
        and "mcp.test.budget-get.v1" in failure
        for failure in failures
    ), failures


def test_registered_tool_no_longer_recorded_fails(
    tmp_path: Path, registry_check: ModuleType
) -> None:
    ghost = mcp_row(f"{MCP_SERVER}/ghost.tool")
    paths = workspace(tmp_path, [("GET", "/v1/agents")], WorkspaceSpec(mcp_tools=[ghost]))
    failures = registry_check.check(paths)
    assert any(
        failure.startswith(f"stale-registration: mcp tool {MCP_SERVER}/ghost.tool ")
        for failure in failures
    )


def test_mcp_contract_id_must_match_the_derivation(
    tmp_path: Path, registry_check: ModuleType
) -> None:
    row = mcp_row(contract_id="mcp.test.invented.v1")
    paths = workspace(tmp_path, [("GET", "/v1/agents")], WorkspaceSpec(mcp_tools=[row]))
    failures = registry_check.check(paths)
    assert any(failure.startswith(f"contract-id-mismatch: {MCP_TOOL_KEY} ") for failure in failures)


def test_mcp_server_field_must_match_the_key(tmp_path: Path, registry_check: ModuleType) -> None:
    row = mcp_row(server="ibex-mcp-other")
    paths = workspace(tmp_path, [("GET", "/v1/agents")], WorkspaceSpec(mcp_tools=[row]))
    failures = registry_check.check(paths)
    assert any(failure.startswith(f"server-mismatch: {MCP_TOOL_KEY} ") for failure in failures)


def test_missing_mcp_record_fails(tmp_path: Path, registry_check: ModuleType) -> None:
    paths = workspace(tmp_path, [("GET", "/v1/agents")])
    missing = tmp_path / "absent-mcp_tools.json"
    broken = model.RegistryPaths(
        inventory=paths.inventory,
        registry=paths.registry,
        doc=paths.doc,
        proto_root=paths.proto_root,
        mcp_records=((MCP_SERVER, missing),),
        root=paths.root,
    )
    failures = registry_check.check(broken)
    assert any(failure.startswith("missing-mcp-record: ") for failure in failures)
