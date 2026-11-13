"""Unit tests for the gRPC half of the contract registry check (P0-14 / W5.3).

``grpc_methods`` rows are derived from the proto tree, so these tests pin three
things: the derivation itself, the coverage in both directions (a declared rpc
needs a row, a row needs a declared rpc), and the service index cross-check that
ties ``out_of_scope.grpc`` to the method rows.

The REST and MCP halves live in ``test_contract_registry.py`` and
``test_contract_registry_mcp.py``; the workspace builder they all share is in
``contract_registry_test_support.py``.
"""

from __future__ import annotations

import json
from pathlib import Path
from types import ModuleType

import pytest

from tests.unit.contract_registry_test_support import (
    GRPC_METHOD_KEY,
    PROTO_SOURCE,
    WorkspaceSpec,
    cli,
    derive,
    grpc_index,
    grpc_row,
    mcp,
    model,
    proto,
    save_registry,
    workspace,
    workspace_with_registry,
)


@pytest.fixture(scope="module")
def registry_check() -> ModuleType:
    """The CLI module: ``check``, ``main``, and the committed paths."""
    return cli


def test_committed_registry_covers_every_rpc_and_mcp_tool() -> None:
    """The committed registry names every declared rpc and every recorded tool."""
    registry = json.loads(model.RegistryPaths.registry.read_text(encoding="utf-8"))

    rpcs = proto.proto_rpc_methods(model.RegistryPaths.proto_root)
    registered_rpcs = {row["key"]: row for row in registry["grpc_methods"]}
    assert sorted(registered_rpcs) == sorted(rpcs)
    for key, row in registered_rpcs.items():
        assert row["contract_id"] == derive.grpc_contract_id(key)
        assert row["status"] == "shipped"
        assert row["owner"] != model.SCAFFOLD_OWNER
        assert (model.REPO_ROOT / row["evidence"]).is_file()

    surfaces, failures = mcp.load_mcp_surfaces(model.RegistryPaths.mcp_records)
    assert failures == []
    recorded = {f"{server}/{tool}" for server, (_path, tools) in surfaces.items() for tool in tools}
    registered_tools = {row["key"]: row for row in registry["mcp_tools"]}
    assert sorted(registered_tools) == sorted(recorded)
    for key, row in registered_tools.items():
        server, tool = derive.mcp_tool_parts(key)
        assert row["server"] == server
        assert row["contract_id"] == derive.mcp_contract_id(server, tool)
        assert (model.REPO_ROOT / row["evidence"]).is_file()


def test_rpc_derivation_is_mechanical() -> None:
    assert (
        derive.grpc_contract_id("ibex.auth.v1.AuthService.ValidateToken")
        == "grpc.auth.validate-token.v1"
    )
    assert (
        derive.grpc_contract_id("ibex.auth.v1.AuthService.BeginTotpEnrollment")
        == "grpc.auth.begin-totp-enrollment.v1"
    )
    assert (
        derive.grpc_contract_id("ibex.context.v1.ContextAssemblyService.AssembleContext")
        == "grpc.context.assemble-context.v1"
    )
    assert derive.grpc_contract_id("nonsense") == ""


def test_an_indented_service_declaration_is_read(
    tmp_path: Path, registry_check: ModuleType
) -> None:
    """Proto allows an indented declaration; missing one would hide every rpc it declares."""
    indented = PROTO_SOURCE.replace("service TestService {", "\tservice TestService {")
    assert proto.service_bodies(indented) == proto.service_bodies(PROTO_SOURCE)

    paths = workspace(tmp_path, [("GET", "/v1/agents")], WorkspaceSpec(grpc_methods=[]))
    (paths.proto_root / "test.proto").write_text(indented, encoding="utf-8")
    assert any(
        failure.startswith(f"missing-registration: rpc {GRPC_METHOD_KEY} ")
        for failure in registry_check.check(paths)
    )


def test_rpc_declared_but_not_registered_fails(tmp_path: Path, registry_check: ModuleType) -> None:
    """A new rpc cannot land without a row: the method is named in the failure."""
    paths = workspace(tmp_path, [("GET", "/v1/agents")], WorkspaceSpec(grpc_methods=[]))
    failures = registry_check.check(paths)
    assert any(
        failure.startswith(f"missing-registration: rpc {GRPC_METHOD_KEY} ")
        and "grpc.test.ping.v1" in failure
        for failure in failures
    ), failures


def test_registered_rpc_that_no_longer_exists_fails(
    tmp_path: Path, registry_check: ModuleType
) -> None:
    ghost = "ibex.test.v1.TestService.Ghost"
    paths = workspace(
        tmp_path,
        [("GET", "/v1/agents")],
        WorkspaceSpec(grpc_methods=[grpc_row(ghost)]),
    )
    failures = registry_check.check(paths)
    assert any(failure.startswith(f"stale-registration: rpc {ghost} ") for failure in failures)


def test_rpc_contract_id_must_match_the_derivation(
    tmp_path: Path, registry_check: ModuleType
) -> None:
    row = grpc_row(contract_id="grpc.test.invented.v1")
    paths = workspace(tmp_path, [("GET", "/v1/agents")], WorkspaceSpec(grpc_methods=[row]))
    failures = registry_check.check(paths)
    assert any(
        failure.startswith(f"contract-id-mismatch: {GRPC_METHOD_KEY} ") for failure in failures
    )


def test_registered_service_without_method_rows_fails(
    tmp_path: Path, registry_check: ModuleType
) -> None:
    paths = workspace(tmp_path, [("GET", "/v1/agents")], WorkspaceSpec(grpc_methods=[]))
    failures = registry_check.check(paths)
    assert any(
        failure.startswith("method-less-service: ibex.test.v1.TestService ") for failure in failures
    )


def test_service_with_method_rows_must_be_registered(
    tmp_path: Path, registry_check: ModuleType
) -> None:
    paths, registry = workspace_with_registry(tmp_path)
    grpc_index(registry)["registered_services"] = []
    save_registry(paths, registry)
    failures = registry_check.check(paths)
    assert any(
        failure.startswith("unregistered-service: ibex.test.v1.TestService ")
        for failure in failures
    )


def test_unaccounted_proto_service_fails(tmp_path: Path, registry_check: ModuleType) -> None:
    paths = workspace(tmp_path, [("GET", "/v1/agents")])
    registry = json.loads(paths.registry.read_text(encoding="utf-8"))
    registry["out_of_scope"]["grpc"]["registered_services"] = []
    save_registry(paths, registry)
    assert any(
        failure.startswith("unaccounted-proto-service: ibex.test.v1.TestService ")
        for failure in registry_check.check(paths)
    )


def test_stale_proto_registration_fails(tmp_path: Path, registry_check: ModuleType) -> None:
    """A registered service that the proto tree does not define is a stale claim."""
    paths, registry = workspace_with_registry(tmp_path)
    grpc_index(registry)["registered_services"].append(
        {
            "service": "ibex.test.v1.GhostService",
            "contract_id": "principal-context.v1",
            "owner": "api",
        }
    )
    save_registry(paths, registry)
    assert registry_check.check(paths) == [
        (
            "stale-proto-registration: ibex.test.v1.GhostService is registered but no such "
            "service exists under packages/proto/proto"
        )
    ]


@pytest.mark.parametrize(
    ("tracked_by", "expected"),
    [
        (
            "",
            [
                "empty-field: out_of_scope.grpc.tracked_by must name the owner item",
                "unknown-enum: out_of_scope.grpc.tracked_by is ''; expected 'P0-12'",
            ],
        ),
        ("W5.1", ["unknown-enum: out_of_scope.grpc.tracked_by is 'W5.1'; expected 'P0-12'"]),
    ],
)
def test_invalid_grpc_tracked_by_fails(
    tmp_path: Path, registry_check: ModuleType, tracked_by: str, expected: list[str]
) -> None:
    """`tracked_by` must name the live owner item; empty and unknown values both fail."""
    paths, registry = workspace_with_registry(tmp_path)
    grpc_index(registry)["tracked_by"] = tracked_by
    save_registry(paths, registry)
    assert sorted(registry_check.check(paths)) == sorted(expected)


def test_declared_out_accepts_a_proto_service_that_is_not_registered(
    tmp_path: Path, registry_check: ModuleType
) -> None:
    """`declared_out` is the one explicit alternative to registering a service."""
    paths, registry = workspace_with_registry(tmp_path)
    grpc = grpc_index(registry)
    grpc["registered_services"] = []
    registry["grpc_methods"] = []
    save_registry(paths, registry)

    failures = registry_check.check(paths)
    unaccounted = [
        failure
        for failure in failures
        if failure.startswith("unaccounted-proto-service: ibex.test.v1.TestService ")
    ]
    assert len(unaccounted) == 1, failures
    assert unaccounted[0].endswith("out_of_scope.grpc.declared_out")

    grpc["declared_out"] = ["ibex.test.v1.TestService"]
    save_registry(paths, registry)
    assert registry_check.check(paths) == []


def test_declared_out_conflicts_with_a_registered_service(
    tmp_path: Path, registry_check: ModuleType
) -> None:
    """A service cannot be both accounted for and declared out."""
    paths, registry = workspace_with_registry(tmp_path)
    grpc_index(registry)["declared_out"] = ["ibex.test.v1.TestService"]
    save_registry(paths, registry)
    assert registry_check.check(paths) == [
        (
            "declared-out-conflict: ibex.test.v1.TestService is listed in "
            "out_of_scope.grpc.declared_out but is also registered or carries grpc_methods rows"
        )
    ]


@pytest.mark.parametrize("field", ["registered_services", "declared_out"])
def test_non_list_grpc_field_fails(tmp_path: Path, registry_check: ModuleType, field: str) -> None:
    """Both arrays are required; a scalar or object in their place is a missing field."""
    paths, registry = workspace_with_registry(tmp_path)
    grpc_index(registry)[field] = {"not": "a list"}
    save_registry(paths, registry)
    assert registry_check.check(paths) == [
        f"missing-field: out_of_scope.grpc.{field} must be an array"
    ]
