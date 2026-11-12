"""Unit tests for the mounted REST route registry check (P0-14 / W5.3).

The first tests assert the committed registry against the committed inventory and
contract document. The rest build a synthetic workspace in ``tmp_path`` so each
failure mode is isolated; none of them touch PostgreSQL, the app, or the tree.

The scaffolding tests exist to prove the gate cannot be laundered: flipping
``status`` to ``shipped`` is not enough, because the scaffolded owner sentinel and
a non-existent evidence path keep ``--check`` red until a human decides both.
"""

from __future__ import annotations

import importlib.util
import json
import re
import sys
from dataclasses import dataclass
from pathlib import Path
from types import ModuleType
from typing import Any

import pytest

_SCRIPT = Path(__file__).resolve().parents[2] / "scripts" / "check_contract_registry.py"
# The script imports its sibling ``contract_ids`` module the way it does when run
# directly (the script directory is on ``sys.path``); mirror that for the import below.
sys.path.insert(0, str(_SCRIPT.parent))
_ROUTER_SOURCE = "services/api/app/routers/agents.py"
_PROTO_SOURCE = """syntax = "proto3";

package ibex.test.v1;

service TestService {
  rpc Ping(PingRequest) returns (PingReply);
}
"""

_DOC_ROW = re.compile(r"^\| `([a-z0-9.-]+\.v1)` \| `([A-Z]+) (/[^`]+)` \| (\w+) \|$", re.MULTILINE)

# Stable committed rows whose IDs encode a derivation decision rather than an
# incidental position: a scope whose removal leaves no other static segment
# (``agents``), a scope-dropped nested collection (``providers``), and a beta
# operator route. They are pinned by route key so a route addition costs no edit
# while a derivation change that rewrites an existing ID still fails.
_PINNED_CONTRACT_IDS = {
    "DELETE /v1/agents/{agent_id}": "management.agents.delete.v1",
    "GET /v1/organizations/{org_id}/providers": "management.providers.read.v1",
    "GET /v1/operator/platform/health": "operator.platform.health.v1",
}


@pytest.fixture(scope="module")
def registry_check() -> ModuleType:
    spec = importlib.util.spec_from_file_location("check_contract_registry", _SCRIPT)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


@dataclass(frozen=True)
class _RowSpec:
    """A row with the human decisions a scaffold cannot make, recorded explicitly."""

    method: str
    path: str
    owner: str = "api"
    stability: str = "stable"
    status: str = "shipped"
    evidence: str = _ROUTER_SOURCE


@dataclass(frozen=True)
class _WorkspaceSpec:
    """Optional overrides for the synthetic registry workspace."""

    rows: list[dict[str, str]] | None = None
    doc_ids: list[str] | None = None


def _row(module: ModuleType, spec: _RowSpec) -> dict[str, str]:
    row = module.scaffold_row(spec.method, spec.path, spec.evidence)
    row.update(
        {
            "owner": spec.owner,
            "stability": spec.stability,
            "status": spec.status,
            "evidence": spec.evidence,
        }
    )
    return row


def _workspace(
    tmp_path: Path,
    module: ModuleType,
    routes: list[tuple[str, str]],
    spec: _WorkspaceSpec | None = None,
) -> object:
    options = spec or _WorkspaceSpec()
    inventory = [
        {"methods": [method], "path": path, "source": _ROUTER_SOURCE} for method, path in routes
    ]
    inventory_path = tmp_path / "route_inventory.json"
    inventory_path.write_text(json.dumps(inventory), encoding="utf-8")

    registry_rows = (
        options.rows
        if options.rows is not None
        else [_row(module, _RowSpec(m, p)) for m, p in routes]
    )
    registry_rows = sorted(registry_rows, key=lambda row: row["key"])
    documented = (
        options.doc_ids
        if options.doc_ids is not None
        else [row["contract_id"] for row in registry_rows]
    )
    doc = tmp_path / "contracts.md"
    doc.write_text(
        "\n".join(f"`{contract_id}`" for contract_id in documented) + "\n`principal-context.v1`\n",
        encoding="utf-8",
    )

    proto_root = tmp_path / "proto"
    proto_root.mkdir()
    (proto_root / "test.proto").write_text(_PROTO_SOURCE, encoding="utf-8")

    # Evidence paths are resolved against the workspace root, so every row that
    # cites the router source needs a real file there.
    evidence_file = tmp_path / _ROUTER_SOURCE
    evidence_file.parent.mkdir(parents=True, exist_ok=True)
    evidence_file.write_text("", encoding="utf-8")

    registry = {
        "schema": module.SCHEMA,
        "routes": registry_rows,
        "out_of_scope": {
            "grpc": {
                "reason": "gRPC shapes are gated by buf-breaking (W5.1) and P0-12.",
                "tracked_by": "P0-12",
                "registered_services": [
                    {
                        "service": "ibex.test.v1.TestService",
                        "contract_id": "principal-context.v1",
                        "owner": "api",
                    }
                ],
                "declared_out": [],
            },
            "mcp_tools": {
                "reason": "MCP tool schemas are gated by the descriptor diff (W5.5).",
                "tracked_by": "W5.5",
            },
        },
    }
    registry_path = tmp_path / "rest-route-registry.json"
    registry_path.write_text(json.dumps(registry, indent=2) + "\n", encoding="utf-8")
    return module.RegistryPaths(
        inventory=inventory_path,
        registry=registry_path,
        doc=doc,
        proto_root=proto_root,
        root=tmp_path,
    )


def _write_registry_rows(paths: object, rows: list[dict[str, str]]) -> None:
    registry = json.loads(paths.registry.read_text(encoding="utf-8"))
    registry["routes"] = rows
    paths.registry.write_text(json.dumps(registry, indent=2) + "\n", encoding="utf-8")


def test_committed_registry_covers_every_mounted_route(registry_check: ModuleType) -> None:
    failures = registry_check.check()
    assert failures == []

    inventory = json.loads(registry_check.RegistryPaths.inventory.read_text(encoding="utf-8"))
    mounted = registry_check.mounted_keys(inventory)
    registry = json.loads(registry_check.RegistryPaths.registry.read_text(encoding="utf-8"))
    rows = registry["routes"]

    assert mounted
    assert [row["key"] for row in rows] == mounted
    assert len({row["contract_id"] for row in rows}) == len(rows)
    for row in rows:
        assert row["status"] == "shipped"
        assert row["stability"] in registry_check.STABILITIES
        assert row["owner"]
        assert row["evidence"]
        assert row["contract_id"]
        assert row["owner"] != registry_check.SCAFFOLD_OWNER
        assert (registry_check.REPO_ROOT / row["evidence"]).exists()
        method, _, path = row["key"].partition(" ")
        assert row["contract_id"] == registry_check.derive_contract_id(method, path)


@pytest.mark.parametrize(
    "candidate",
    [
        "management.agents.read.v1",
        "principal-context.v1",
        "operator.platform.health.v1",
        "a.v1",
        "a.1.v1",
    ],
)
def test_contract_id_language_accepts_the_documented_shape(
    registry_check: ModuleType, candidate: str
) -> None:
    assert registry_check.documented_contract_ids(f"`{candidate}`") == {candidate}


@pytest.mark.parametrize(
    "candidate",
    [
        "management.agents.read",
        "management.agents.read.v2",
        "management..read.v1",
        "management.agents.read.v1x",
        ".v1",
        "management.agents.read_v1",
    ],
)
def test_contract_id_language_rejects_near_misses(
    registry_check: ModuleType, candidate: str
) -> None:
    assert registry_check.documented_contract_ids(f"`{candidate}`") == frozenset()


def test_contract_ids_are_extracted_from_prose(registry_check: ModuleType) -> None:
    """The document is prose plus tables; the ID is picked out of either."""
    text = "The route `management.agents.read.v1` is documented; see also v1 (not an ID)."
    assert registry_check.documented_contract_ids(text) == {"management.agents.read.v1"}


def test_check_flag_is_accepted_and_passes_on_the_committed_registry(
    registry_check: ModuleType, capsys: pytest.CaptureFixture[str]
) -> None:
    """`--check` names the default mode; it must not be an "unrecognized argument"."""
    assert registry_check.main(["--check"]) == 0
    captured = capsys.readouterr()
    assert "contract registry is complete" in captured.out
    # The alias is a mode flag, so it cannot be combined with the scaffolding mode.
    with pytest.raises(SystemExit) as conflict:
        registry_check.main(["--check", "--write"])
    assert conflict.value.code == 2


def _documented_rows(doc: str) -> list[tuple[str, str, str]]:
    """Return ``(contract_id, route key, stability)`` for each route table row."""
    return [
        (contract_id, f"{method} {path}", stability)
        for contract_id, method, path, stability in _DOC_ROW.findall(doc)
    ]


def _doc_mismatches(
    documented: list[tuple[str, str, str]], rows: list[dict[str, str]]
) -> list[str]:
    """Compare the document table with the registry by key, not by position."""
    doc_stability, doc_route = _documented_columns(documented)
    registered = {row["contract_id"]: row for row in rows}
    problems = _duplicate_doc_failures(doc_stability, documented)
    for contract_id in sorted(doc_stability):
        row = registered.get(contract_id)
        if row is None:
            problems.append(f"stale-doc-row: {contract_id} is documented but not registered")
            continue
        problems.extend(_column_failures(contract_id, doc_stability, doc_route, row))
    problems.extend(_missing_doc_failures(registered, doc_stability))
    return problems


def _documented_columns(
    documented: list[tuple[str, str, str]],
) -> tuple[dict[str, str], dict[str, str]]:
    doc_stability = {contract_id: stability for contract_id, _, stability in documented}
    doc_route = {contract_id: key for contract_id, key, _ in documented}
    return doc_stability, doc_route


def _duplicate_doc_failures(
    doc_stability: dict[str, str], documented: list[tuple[str, str, str]]
) -> list[str]:
    if len(doc_stability) == len(documented):
        return []
    return ["duplicate-doc-row: the contract document repeats a contract ID"]


def _column_failures(
    contract_id: str,
    doc_stability: dict[str, str],
    doc_route: dict[str, str],
    row: dict[str, str],
) -> list[str]:
    problems: list[str] = []
    stability = doc_stability[contract_id]
    if stability != row["stability"]:
        problems.append(
            f"stability-mismatch: {contract_id} is {stability} in the document and "
            f"{row['stability']} in the registry"
        )
    route = doc_route[contract_id]
    if route != row["key"]:
        problems.append(
            f"route-mismatch: {contract_id} is {route} in the document and "
            f"{row['key']} in the registry"
        )
    return problems


def _missing_doc_failures(
    registered: dict[str, dict[str, str]], doc_stability: dict[str, str]
) -> list[str]:
    return [
        f"missing-doc-row: {contract_id} is registered but not documented"
        for contract_id in sorted(registered)
        if contract_id not in doc_stability
    ]


def _doc_line(contract_id: str, key: str, stability: str) -> str:
    method, _, path = key.partition(" ")
    return f"| `{contract_id}` | `{method} {path}` | {stability} |"


def test_contract_document_table_matches_the_registry(registry_check: ModuleType) -> None:
    doc = registry_check.RegistryPaths.doc.read_text(encoding="utf-8")
    registry = json.loads(registry_check.RegistryPaths.registry.read_text(encoding="utf-8"))
    rows = registry["routes"]

    # Order is a property of the JSON, not of the human-maintained table; the table
    # is compared by contract ID so a harmless reorder does not fail the suite.
    keys = [row["key"] for row in rows]
    assert keys == sorted(keys)
    assert [row["contract_id"] for row in rows] == [
        row["contract_id"] for row in sorted(rows, key=lambda row: row["key"])
    ]

    documented = _documented_rows(doc)
    assert len(documented) == len(rows)
    assert _doc_mismatches(documented, rows) == []


def test_document_comparison_tolerates_a_reorder(registry_check: ModuleType) -> None:
    rows = [
        _row(registry_check, _RowSpec("GET", "/v1/agents")),
        _row(registry_check, _RowSpec("POST", "/v1/agents")),
        _row(registry_check, _RowSpec("DELETE", "/v1/agents/{agent_id}")),
    ]
    documented = [(row["contract_id"], row["key"], row["stability"]) for row in rows]
    assert _doc_mismatches(list(reversed(documented)), rows) == []


def test_document_with_a_stale_contract_id_fails(registry_check: ModuleType) -> None:
    row = _row(registry_check, _RowSpec("GET", "/v1/agents"))
    documented = _documented_rows(
        _doc_line(row["contract_id"], row["key"], row["stability"])
        + "\n"
        + _doc_line("management.ghosts.read.v1", "GET /v1/ghosts", "stable")
    )
    assert _doc_mismatches(documented, [row]) == [
        "stale-doc-row: management.ghosts.read.v1 is documented but not registered"
    ]


def test_document_missing_a_contract_id_fails(registry_check: ModuleType) -> None:
    row = _row(registry_check, _RowSpec("GET", "/v1/agents"))
    assert _doc_mismatches(_documented_rows(""), [row]) == [
        f"missing-doc-row: {row['contract_id']} is registered but not documented"
    ]


def test_document_with_a_wrong_stability_fails(registry_check: ModuleType) -> None:
    row = _row(registry_check, _RowSpec("GET", "/v1/agents"))
    documented = _documented_rows(_doc_line(row["contract_id"], row["key"], "beta"))
    assert _doc_mismatches(documented, [row]) == [
        f"stability-mismatch: {row['contract_id']} is beta in the document and stable in the registry"
    ]


@pytest.mark.parametrize(
    ("method", "path", "expected"),
    [
        ("GET", "/v1/agents", "management.agents.read.v1"),
        ("GET", "/v1/agents/{agent_id}", "management.agents.get.v1"),
        ("POST", "/v1/agents/{agent_id}/activate", "management.agents.activate.v1"),
        (
            "GET",
            "/v1/organizations/{org_id}/capture-policies",
            "management.capture-policies.read.v1",
        ),
        ("POST", "/v1/organizations/{org_id}/suspend", "management.organizations.suspend.v1"),
        ("GET", "/v1/operator/platform/health", "operator.platform.health.v1"),
        ("POST", "/v1/operator/session/login", "operator.session.login.v1"),
        ("GET", "/health", "platform.health.read.v1"),
    ],
)
def test_derivation_rule_is_mechanical(
    registry_check: ModuleType, method: str, path: str, expected: str
) -> None:
    assert registry_check.derive_contract_id(method, path) == expected


def test_synthetic_workspace_baseline_passes(tmp_path: Path, registry_check: ModuleType) -> None:
    paths = _workspace(tmp_path, registry_check, [("GET", "/v1/agents")])
    assert registry_check.check(paths) == []


def test_missing_mounted_route_fails(tmp_path: Path, registry_check: ModuleType) -> None:
    paths = _workspace(
        tmp_path,
        registry_check,
        [("GET", "/v1/agents"), ("POST", "/v1/agents")],
        _WorkspaceSpec(rows=[_row(registry_check, _RowSpec("GET", "/v1/agents"))]),
    )
    failures = registry_check.check(paths)
    assert any(
        failure.startswith("missing-registration: POST /v1/agents ")
        and "management.agents.create.v1" in failure
        for failure in failures
    )


def test_stale_key_fails(tmp_path: Path, registry_check: ModuleType) -> None:
    paths = _workspace(
        tmp_path,
        registry_check,
        [("GET", "/v1/agents")],
        _WorkspaceSpec(
            rows=[
                _row(registry_check, _RowSpec("GET", "/v1/agents")),
                _row(registry_check, _RowSpec("GET", "/v1/ghosts")),
            ]
        ),
    )
    assert any(
        failure.startswith("stale-registration: GET /v1/ghosts ")
        for failure in registry_check.check(paths)
    )


def test_contract_id_missing_from_contract_document_fails(
    tmp_path: Path, registry_check: ModuleType
) -> None:
    row = _row(registry_check, _RowSpec("GET", "/v1/agents"))
    paths = _workspace(
        tmp_path,
        registry_check,
        [("GET", "/v1/agents")],
        _WorkspaceSpec(rows=[row], doc_ids=[]),
    )
    failures = registry_check.check(paths)
    assert any(
        failure.startswith(f"undocumented-contract: {row['contract_id']} ") for failure in failures
    )
    # The message names the document actually checked, not a hard-coded default.
    assert any(paths.doc.as_posix() in failure for failure in failures)


def _checked_rows(tmp_path: Path, module: ModuleType, spec: _WorkspaceSpec) -> list[str]:
    """Build a single-route workspace and return every registry failure."""
    return module.check(_workspace(tmp_path, module, [("GET", "/v1/agents")], spec))


def _registry_paths(tmp_path: Path, module: ModuleType) -> tuple[object, dict[str, Any]]:
    """Build the passing baseline workspace and return it with its parsed registry."""
    paths = _workspace(tmp_path, module, [("GET", "/v1/agents")])
    return paths, json.loads(paths.registry.read_text(encoding="utf-8"))


def _save_registry(paths: object, registry: dict[str, Any]) -> None:
    """Persist an edited registry so the next ``check`` reads it back."""
    paths.registry.write_text(json.dumps(registry, indent=2) + "\n", encoding="utf-8")


def _grpc_block(registry: dict[str, Any]) -> dict[str, Any]:
    """The ``out_of_scope.grpc`` object, asserted to exist in the baseline workspace."""
    grpc = registry["out_of_scope"]["grpc"]
    assert isinstance(grpc, dict)
    return grpc


def test_invented_contract_id_fails(tmp_path: Path, registry_check: ModuleType) -> None:
    row = _row(registry_check, _RowSpec("GET", "/v1/agents"))
    row["contract_id"] = "management.agents.invented.v1"
    failures = _checked_rows(
        tmp_path,
        registry_check,
        _WorkspaceSpec(rows=[row], doc_ids=["management.agents.invented.v1"]),
    )
    assert any(failure.startswith("contract-id-mismatch: GET /v1/agents ") for failure in failures)


def test_unregistered_status_fails(tmp_path: Path, registry_check: ModuleType) -> None:
    row = _row(registry_check, _RowSpec("GET", "/v1/agents", status="unregistered"))
    failures = _checked_rows(tmp_path, registry_check, _WorkspaceSpec(rows=[row]))
    assert any(failure.startswith("unregistered: GET /v1/agents ") for failure in failures)


def test_unknown_stability_fails(tmp_path: Path, registry_check: ModuleType) -> None:
    row = _row(registry_check, _RowSpec("GET", "/v1/agents", stability="experimental"))
    failures = _checked_rows(tmp_path, registry_check, _WorkspaceSpec(rows=[row]))
    assert any(
        failure.startswith("unknown-enum: GET /v1/agents has stability ") for failure in failures
    )


def test_duplicate_key_fails(tmp_path: Path, registry_check: ModuleType) -> None:
    row = _row(registry_check, _RowSpec("GET", "/v1/agents"))
    failures = _checked_rows(tmp_path, registry_check, _WorkspaceSpec(rows=[row, dict(row)]))
    assert any(failure.startswith("duplicate-key: GET /v1/agents ") for failure in failures)


def test_unknown_schema_fails(tmp_path: Path, registry_check: ModuleType) -> None:
    """The registry declares its own schema version; a different one is not read as this format."""
    paths, registry = _registry_paths(tmp_path, registry_check)
    registry["schema"] = "ibex.contract-registry.v2"
    _save_registry(paths, registry)
    assert registry_check.check(paths) == [
        (
            "unknown-enum: registry schema is 'ibex.contract-registry.v2'; "
            f"expected {registry_check.SCHEMA!r}"
        )
    ]


def test_unsorted_registry_names_the_actual_and_expected_key(
    tmp_path: Path, registry_check: ModuleType
) -> None:
    """The message must say what the row is and what belongs in that position, in that order."""
    paths = _workspace(tmp_path, registry_check, [("GET", "/v1/agents"), ("POST", "/v1/agents")])
    registry = json.loads(paths.registry.read_text(encoding="utf-8"))
    registry["routes"] = list(reversed(registry["routes"]))
    _save_registry(paths, registry)

    failures = registry_check.check(paths)
    assert len(failures) == 1, failures
    message = failures[0]
    assert message.startswith("unsorted-registry: routes[0] ")
    # routes[0] holds POST and the sorted expectation for that position is GET.
    assert "is 'POST /v1/agents'" in message
    assert "expected 'GET /v1/agents'" in message


def test_two_methods_on_one_action_verb_path_collide_on_the_contract_id(
    tmp_path: Path, registry_check: ModuleType
) -> None:
    """``GET`` and ``POST`` on ``.../activate`` derive one ID; the check fails closed.

    The derivation is deliberately not changed to dodge this: it would rewrite the
    committed IDs and the document. This test pins both halves of that decision —
    the collision is reported, and a derivation change that rewrites a pinned
    committed ID cannot pass unnoticed. The row count is not pinned: adding a
    route must not force an edit here.
    """
    collision = "management.agents.activate.v1"
    activate = "/v1/agents/{agent_id}/activate"
    assert registry_check.derive_contract_id("GET", activate) == collision
    assert registry_check.derive_contract_id("POST", activate) == collision

    paths = _workspace(tmp_path, registry_check, [("GET", activate), ("POST", activate)])
    failures = registry_check.check(paths)
    assert len(failures) == 1, failures
    message = failures[0]
    assert message.startswith(f"duplicate-contract: {collision} is claimed by ")
    assert f"GET {activate}" in message
    assert f"POST {activate}" in message

    committed = json.loads(registry_check.RegistryPaths.registry.read_text(encoding="utf-8"))
    rows = committed["routes"]
    # Pin key -> contract ID, not the row count, so legitimate route additions
    # cost no test edit while a rewritten existing ID fails with a readable diff.
    by_key = {row["key"]: row["contract_id"] for row in rows}
    assert len(by_key) == len(rows)
    assert {key: by_key.get(key) for key in _PINNED_CONTRACT_IDS} == _PINNED_CONTRACT_IDS
    assert len({row["contract_id"] for row in rows}) == len(rows)
    assert len(rows) >= len(_PINNED_CONTRACT_IDS)


def test_unaccounted_proto_service_fails(tmp_path: Path, registry_check: ModuleType) -> None:
    paths = _workspace(tmp_path, registry_check, [("GET", "/v1/agents")])
    registry = json.loads(paths.registry.read_text(encoding="utf-8"))
    registry["out_of_scope"]["grpc"]["registered_services"] = []
    paths.registry.write_text(json.dumps(registry, indent=2) + "\n", encoding="utf-8")
    assert any(
        failure.startswith("unaccounted-proto-service: ibex.test.v1.TestService ")
        for failure in registry_check.check(paths)
    )


def test_stale_proto_registration_fails(tmp_path: Path, registry_check: ModuleType) -> None:
    """A registered service that the proto tree does not define is a stale claim."""
    paths, registry = _registry_paths(tmp_path, registry_check)
    _grpc_block(registry)["registered_services"].append(
        {
            "service": "ibex.test.v1.GhostService",
            "contract_id": "principal-context.v1",
            "owner": "api",
        }
    )
    _save_registry(paths, registry)
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
    paths, registry = _registry_paths(tmp_path, registry_check)
    _grpc_block(registry)["tracked_by"] = tracked_by
    _save_registry(paths, registry)
    assert sorted(registry_check.check(paths)) == sorted(expected)


def test_declared_out_accepts_a_proto_service_that_is_not_registered(
    tmp_path: Path, registry_check: ModuleType
) -> None:
    """`declared_out` is the one explicit alternative to registering a service."""
    paths, registry = _registry_paths(tmp_path, registry_check)
    grpc = _grpc_block(registry)
    grpc["registered_services"] = []
    _save_registry(paths, registry)

    failures = registry_check.check(paths)
    assert len(failures) == 1, failures
    assert failures[0].startswith("unaccounted-proto-service: ibex.test.v1.TestService ")
    assert failures[0].endswith("out_of_scope.grpc.declared_out")

    grpc["declared_out"] = ["ibex.test.v1.TestService"]
    _save_registry(paths, registry)
    assert registry_check.check(paths) == []


@pytest.mark.parametrize("field", ["registered_services", "declared_out"])
def test_non_list_grpc_field_fails(tmp_path: Path, registry_check: ModuleType, field: str) -> None:
    """Both arrays are required; a scalar or object in their place is a missing field."""
    paths, registry = _registry_paths(tmp_path, registry_check)
    _grpc_block(registry)[field] = {"not": "a list"}
    _save_registry(paths, registry)
    assert registry_check.check(paths) == [
        f"missing-field: out_of_scope.grpc.{field} must be an array"
    ]


def test_scaffold_row_invents_nothing(registry_check: ModuleType) -> None:
    row = registry_check.scaffold_row("GET", "/v1/agents", _ROUTER_SOURCE)
    assert row["owner"] == registry_check.SCAFFOLD_OWNER
    assert row["stability"] == registry_check.SCAFFOLD_STABILITY == "internal"
    assert row["status"] == "unregistered"
    assert row["contract_id"] == "management.agents.read.v1"
    assert row["evidence"] == _ROUTER_SOURCE


def test_flipping_status_only_does_not_launder_a_scaffold(
    tmp_path: Path, registry_check: ModuleType
) -> None:
    row = registry_check.scaffold_row("GET", "/v1/agents", _ROUTER_SOURCE)
    row["status"] = "shipped"
    paths = _workspace(
        tmp_path, registry_check, [("GET", "/v1/agents")], _WorkspaceSpec(rows=[row])
    )

    failures = registry_check.check(paths)
    assert any(failure.startswith("unassigned-owner: GET /v1/agents ") for failure in failures), (
        failures
    )

    row["owner"] = "api"
    row["stability"] = "stable"
    _write_registry_rows(paths, [row])
    assert registry_check.check(paths) == []


def test_missing_evidence_path_fails_until_the_file_exists(
    tmp_path: Path, registry_check: ModuleType
) -> None:
    row = _row(
        registry_check, _RowSpec("GET", "/v1/agents", evidence="services/api/app/nowhere.py")
    )
    paths = _workspace(
        tmp_path, registry_check, [("GET", "/v1/agents")], _WorkspaceSpec(rows=[row])
    )
    failures = registry_check.check(paths)
    assert any(
        failure.startswith("missing-evidence: GET /v1/agents ")
        and "services/api/app/nowhere.py" in failure
        for failure in failures
    ), failures

    evidence = tmp_path / row["evidence"]
    evidence.parent.mkdir(parents=True, exist_ok=True)
    evidence.write_text("", encoding="utf-8")
    assert registry_check.check(paths) == []


def _evidence_failure_for(tmp_path: Path, module: ModuleType, evidence: str) -> str:
    """Check a single row citing ``evidence`` and return its one missing-evidence line."""
    row = _row(module, _RowSpec("GET", "/v1/agents", evidence=evidence))
    paths = _workspace(tmp_path, module, [("GET", "/v1/agents")], _WorkspaceSpec(rows=[row]))
    failures = [
        failure
        for failure in module.check(paths)
        if failure.startswith("missing-evidence: GET /v1/agents ")
    ]
    assert len(failures) == 1, failures
    return failures[0]


def test_evidence_absolute_path_outside_the_repository_fails(
    tmp_path: Path, registry_check: ModuleType
) -> None:
    """`exists()` alone accepted any host file; the citation must stay in the tree."""
    outside = Path("/etc/hostname")
    if not outside.is_file():
        pytest.skip("/etc/hostname is not a file on this platform")
    failure = _evidence_failure_for(tmp_path, registry_check, outside.as_posix())
    assert outside.as_posix() in failure
    assert "resolves outside" in failure


def test_evidence_directory_fails(tmp_path: Path, registry_check: ModuleType) -> None:
    """`services/api/app` exists but is a directory, so it cites no code."""
    failure = _evidence_failure_for(tmp_path, registry_check, "services/api/app")
    assert (tmp_path / "services/api/app").is_dir()
    assert "is not a file" in failure
    assert "directory" in failure


def test_evidence_parent_escape_fails(tmp_path: Path, registry_check: ModuleType) -> None:
    """A `../` path that exists outside the root still fails containment."""
    escaped = tmp_path.parent / f"{tmp_path.name}-escaped-evidence.md"
    escaped.write_text("", encoding="utf-8")
    failure = _evidence_failure_for(tmp_path, registry_check, f"../{escaped.name}")
    assert "resolves outside" in failure


def test_evidence_symlink_escaping_the_root_fails(
    tmp_path: Path, registry_check: ModuleType
) -> None:
    """The symlink exists, so only resolution-based containment can reject it."""
    outside = tmp_path.parent / f"{tmp_path.name}-outside-evidence.md"
    outside.write_text("", encoding="utf-8")
    link = tmp_path / "linked-evidence.md"
    try:
        link.symlink_to(outside)
    except (OSError, NotImplementedError):
        pytest.skip("this platform does not allow creating symlinks")
    assert link.exists()
    failure = _evidence_failure_for(tmp_path, registry_check, link.name)
    assert "resolves outside" in failure


def test_evidence_symlink_inside_the_root_is_accepted(
    tmp_path: Path, registry_check: ModuleType
) -> None:
    """Containment is the rule, not "reject every symlink"."""
    link = tmp_path / "linked-evidence.md"
    row = _row(registry_check, _RowSpec("GET", "/v1/agents", evidence=link.name))
    paths = _workspace(
        tmp_path, registry_check, [("GET", "/v1/agents")], _WorkspaceSpec(rows=[row])
    )
    try:
        link.symlink_to(tmp_path / _ROUTER_SOURCE)
    except (OSError, NotImplementedError):
        pytest.skip("this platform does not allow creating symlinks")
    assert registry_check.check(paths) == []


def test_write_scaffolds_unregistered_rows_and_leaves_the_gate_red(
    tmp_path: Path, registry_check: ModuleType
) -> None:
    paths = _workspace(
        tmp_path,
        registry_check,
        [("GET", "/v1/agents"), ("POST", "/v1/agents")],
        _WorkspaceSpec(rows=[_row(registry_check, _RowSpec("GET", "/v1/agents"))]),
    )
    assert (
        registry_check.main(
            [
                "--write",
                "--inventory",
                str(paths.inventory),
                "--registry",
                str(paths.registry),
                "--doc",
                str(paths.doc),
                "--proto-root",
                str(paths.proto_root),
            ]
        )
        == 0
    )

    registry = json.loads(paths.registry.read_text(encoding="utf-8"))
    added = [row for row in registry["routes"] if row["key"] == "POST /v1/agents"]
    assert len(added) == 1
    assert added[0]["status"] == "unregistered"
    assert added[0]["owner"] == registry_check.SCAFFOLD_OWNER
    assert added[0]["stability"] == registry_check.SCAFFOLD_STABILITY
    assert added[0]["contract_id"] == "management.agents.create.v1"

    failures = registry_check.check(paths)
    assert any(failure.startswith("unregistered: POST /v1/agents ") for failure in failures)
    assert any(failure.startswith("unassigned-owner: POST /v1/agents ") for failure in failures)


def test_write_is_atomic(tmp_path: Path, registry_check: ModuleType) -> None:
    paths = _workspace(
        tmp_path,
        registry_check,
        [("GET", "/v1/agents"), ("POST", "/v1/agents")],
        _WorkspaceSpec(rows=[_row(registry_check, _RowSpec("GET", "/v1/agents"))]),
    )
    before = paths.registry.read_text(encoding="utf-8")
    real_replace = registry_check.os.replace

    def _interrupted(src: object, dst: object, *args: object, **kwargs: object) -> None:
        if Path(str(dst)) == paths.registry:
            raise OSError("simulated interruption")
        real_replace(src, dst, *args, **kwargs)

    registry_check.os.replace = _interrupted
    try:
        with pytest.raises(OSError):
            registry_check.scaffold(paths)
    finally:
        registry_check.os.replace = real_replace

    assert paths.registry.read_text(encoding="utf-8") == before
    assert sorted(path.name for path in tmp_path.glob("*.tmp")) == []
