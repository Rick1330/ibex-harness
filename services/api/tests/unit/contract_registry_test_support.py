"""Shared builders for the contract registry unit tests.

The subject modules live beside this one: ``test_contract_registry.py`` covers
the REST surface and the registry file shape, ``test_contract_registry_grpc.py``
the ``grpc_methods`` rows and the service index, and
``test_contract_registry_mcp.py`` the descriptor records and ``mcp_tools`` rows.

Every synthetic-workspace test runs in ``tmp_path``: this module writes one
inventory, registry, contract document, proto tree, and descriptor record there,
so each failure mode is isolated and none of them touch PostgreSQL, the app, or
the tree.

The scripts import their siblings by bare name, the way they do when run
directly, so the scripts directory is put on ``sys.path`` before the modules are
imported below.
"""

from __future__ import annotations

import importlib
import json
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

SCRIPTS = Path(__file__).resolve().parents[2] / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

# Imported after the path is set up, not at the top of the module, because the
# script modules resolve each other by bare name.
cli = importlib.import_module("check_contract_registry")
derive = importlib.import_module("contract_registry_derive")
ids = importlib.import_module("contract_ids")
mcp = importlib.import_module("contract_registry_mcp")
model = importlib.import_module("contract_registry_model")
proto = importlib.import_module("contract_registry_proto")
rest = importlib.import_module("contract_registry_rest")
write = importlib.import_module("contract_registry_write")

ROUTER_SOURCE = "services/api/app/routers/agents.py"
PROTO_SOURCE = """syntax = "proto3";

package ibex.test.v1;

service TestService {
  rpc Ping(PingRequest) returns (PingReply);
}
"""
GRPC_METHOD_KEY = "ibex.test.v1.TestService.Ping"
MCP_SERVER = "ibex-mcp-test"
MCP_TOOL = "budget.get"
MCP_TOOL_KEY = f"{MCP_SERVER}/{MCP_TOOL}"
MCP_RECORD_SCHEMA = "ibex.mcp-tool-descriptor.v1"
EVIDENCE_ID = "principal-context.v1"


@dataclass(frozen=True)
class RowSpec:
    """A row with the human decisions a scaffold cannot make, recorded explicitly."""

    method: str
    path: str
    owner: str = "api"
    stability: str = "stable"
    status: str = "shipped"
    evidence: str = ROUTER_SOURCE


@dataclass(frozen=True)
class WorkspaceSpec:
    """Optional overrides for the synthetic registry workspace."""

    rows: list[dict[str, str]] | None = None
    doc_ids: list[str] | None = None
    grpc_methods: list[dict[str, str]] | None = None
    mcp_tools: list[dict[str, str]] | None = None
    recorded_tools: list[str] | None = None


def route_row(spec: RowSpec) -> dict[str, str]:
    """A REST row whose contract ID is the scaffold derivation, then the spec's decisions."""
    row = write.scaffold_row(spec.method, spec.path, spec.evidence)
    row.update(
        {
            "owner": spec.owner,
            "stability": spec.stability,
            "status": spec.status,
            "evidence": spec.evidence,
        }
    )
    return row


def grpc_row(key: str = GRPC_METHOD_KEY, **overrides: str) -> dict[str, str]:
    """A gRPC row whose contract ID is the derivation, so only the overrides can move it."""
    row = {
        "key": key,
        "contract_id": derive.grpc_contract_id(key),
        "owner": "api",
        "stability": "beta",
        "status": "shipped",
        "evidence": "proto/test.proto",
    }
    row.update(overrides)
    return row


def mcp_row(key: str = MCP_TOOL_KEY, **overrides: str) -> dict[str, str]:
    """An MCP row whose server and contract ID come from the key."""
    parts = derive.mcp_tool_parts(key)
    assert parts is not None
    server, tool = parts
    row = {
        "key": key,
        "contract_id": derive.mcp_contract_id(server, tool),
        "server": server,
        "owner": "api",
        "status": "shipped",
        "evidence": "mcp_tools.json",
    }
    row.update(overrides)
    return row


def _sorted_rows(rows: list[dict[str, str]]) -> list[dict[str, str]]:
    return sorted(rows, key=lambda row: row["key"])


def _route_rows(routes: list[tuple[str, str]], spec: WorkspaceSpec) -> list[dict[str, str]]:
    if spec.rows is not None:
        return _sorted_rows(spec.rows)
    return _sorted_rows([route_row(RowSpec(method, path)) for method, path in routes])


def _write_inventory(tmp_path: Path, routes: list[tuple[str, str]]) -> Path:
    inventory = [
        {"methods": [method], "path": path, "source": ROUTER_SOURCE} for method, path in routes
    ]
    path = tmp_path / "route_inventory.json"
    path.write_text(json.dumps(inventory), encoding="utf-8")
    return path


def _documented_ids(rows: list[dict[str, str]], spec: WorkspaceSpec) -> list[str]:
    if spec.doc_ids is not None:
        return spec.doc_ids
    return [row["contract_id"] for row in rows]


def _write_doc(tmp_path: Path, documented: list[str]) -> Path:
    doc = tmp_path / "contracts.md"
    doc.write_text(
        "\n".join(f"`{contract_id}`" for contract_id in documented) + f"\n`{EVIDENCE_ID}`\n",
        encoding="utf-8",
    )
    return doc


def _write_proto(tmp_path: Path) -> Path:
    proto_root = tmp_path / "proto"
    proto_root.mkdir()
    (proto_root / "test.proto").write_text(PROTO_SOURCE, encoding="utf-8")
    return proto_root


def _write_mcp_record(tmp_path: Path, spec: WorkspaceSpec) -> Path:
    recorded = spec.recorded_tools if spec.recorded_tools is not None else [MCP_TOOL]
    path = tmp_path / "mcp_tools.json"
    path.write_text(
        json.dumps(
            {
                "generator": {"schema": MCP_RECORD_SCHEMA},
                "tools": [{"name": name} for name in recorded],
            }
        ),
        encoding="utf-8",
    )
    return path


def _out_of_scope() -> dict[str, object]:
    return {
        "grpc": {
            "reason": "gRPC shapes are gated by buf-breaking (W5.1) and P0-12.",
            "tracked_by": "P0-12",
            "registered_services": [
                {
                    "service": "ibex.test.v1.TestService",
                    "contract_id": EVIDENCE_ID,
                    "owner": "api",
                }
            ],
            "declared_out": [],
        },
        "mcp_tools": {
            "reason": "MCP tool schemas are gated by the descriptor diff (W5.5).",
            "tracked_by": "W5.5",
        },
    }


def _grpc_rows(spec: WorkspaceSpec) -> list[dict[str, str]]:
    if spec.grpc_methods is not None:
        return _sorted_rows(spec.grpc_methods)
    return [grpc_row()]


def _mcp_rows(spec: WorkspaceSpec) -> list[dict[str, str]]:
    if spec.mcp_tools is not None:
        return _sorted_rows(spec.mcp_tools)
    return [mcp_row()]


def _write_registry(tmp_path: Path, rows: list[dict[str, str]], spec: WorkspaceSpec) -> Path:
    registry = {
        "schema": model.SCHEMA,
        "routes": rows,
        "grpc_methods": _grpc_rows(spec),
        "mcp_tools": _mcp_rows(spec),
        "out_of_scope": _out_of_scope(),
    }
    path = tmp_path / "rest-route-registry.json"
    path.write_text(json.dumps(registry, indent=2) + "\n", encoding="utf-8")
    return path


def _write_evidence(tmp_path: Path) -> None:
    """Evidence resolves against the workspace root, so every cited source must exist there."""
    evidence_file = tmp_path / ROUTER_SOURCE
    evidence_file.parent.mkdir(parents=True, exist_ok=True)
    evidence_file.write_text("", encoding="utf-8")


def workspace(
    tmp_path: Path,
    routes: list[tuple[str, str]],
    spec: WorkspaceSpec | None = None,
) -> object:
    """Write a synthetic workspace and return the paths that describe it."""
    options = spec or WorkspaceSpec()
    rows = _route_rows(routes, options)
    inventory_path = _write_inventory(tmp_path, routes)
    doc = _write_doc(tmp_path, _documented_ids(rows, options))
    proto_root = _write_proto(tmp_path)
    mcp_record_path = _write_mcp_record(tmp_path, options)
    registry_path = _write_registry(tmp_path, rows, options)
    _write_evidence(tmp_path)
    return model.RegistryPaths(
        inventory=inventory_path,
        registry=registry_path,
        doc=doc,
        proto_root=proto_root,
        mcp_records=((MCP_SERVER, mcp_record_path),),
        root=tmp_path,
    )


def checked_rows(tmp_path: Path, spec: WorkspaceSpec) -> list[str]:
    """Build a single-route workspace and return every registry failure."""
    return cli.check(workspace(tmp_path, [("GET", "/v1/agents")], spec))


def workspace_with_registry(tmp_path: Path) -> tuple[object, dict[str, Any]]:
    """Build the passing baseline workspace and return it with its parsed registry."""
    paths = workspace(tmp_path, [("GET", "/v1/agents")])
    return paths, json.loads(paths.registry.read_text(encoding="utf-8"))


def save_registry(paths: object, registry: dict[str, Any]) -> None:
    """Persist an edited registry so the next ``check`` reads it back."""
    paths.registry.write_text(json.dumps(registry, indent=2) + "\n", encoding="utf-8")


def write_registry_rows(paths: object, rows: list[dict[str, str]]) -> None:
    registry = json.loads(paths.registry.read_text(encoding="utf-8"))
    registry["routes"] = rows
    save_registry(paths, registry)


def grpc_index(registry: dict[str, Any]) -> dict[str, Any]:
    """The ``out_of_scope.grpc`` object, asserted to exist in the baseline workspace."""
    grpc = registry["out_of_scope"]["grpc"]
    assert isinstance(grpc, dict)
    return grpc
