"""Unit tests for the REST route registry check and the registry file shape (P0-14 / W5.3).

The first tests assert the committed registry against the committed inventory and
contract document. The rest build a synthetic workspace in ``tmp_path`` so each
failure mode is isolated; none of them touch PostgreSQL, the app, or the tree.

The scaffolding tests exist to prove the gate cannot be laundered: flipping
``status`` to ``shipped`` is not enough, because the scaffolded owner sentinel and
a non-existent evidence path keep ``--check`` red until a human decides both.

The gRPC and MCP halves live in ``test_contract_registry_grpc.py`` and
``test_contract_registry_mcp.py``.
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from types import ModuleType

import pytest

from tests.unit.contract_registry_test_support import (
    ROUTER_SOURCE,
    RowSpec,
    WorkspaceSpec,
    checked_rows,
    cli,
    derive,
    ids,
    model,
    rest,
    route_row,
    save_registry,
    workspace,
    workspace_with_registry,
    write,
    write_registry_rows,
)

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
    """The CLI module: ``check``, ``main``, and the committed paths."""
    return cli


def test_committed_registry_covers_every_mounted_route(registry_check: ModuleType) -> None:
    failures = registry_check.check()
    assert failures == []

    inventory = json.loads(model.RegistryPaths.inventory.read_text(encoding="utf-8"))
    mounted = rest.mounted_keys(inventory)
    registry = json.loads(model.RegistryPaths.registry.read_text(encoding="utf-8"))
    rows = registry["routes"]

    assert mounted
    assert [row["key"] for row in rows] == mounted
    assert len({row["contract_id"] for row in rows}) == len(rows)
    for row in rows:
        assert row["status"] == "shipped"
        assert row["stability"] in model.STABILITIES
        assert row["owner"]
        assert row["evidence"]
        assert row["contract_id"]
        assert row["owner"] != model.SCAFFOLD_OWNER
        assert (model.REPO_ROOT / row["evidence"]).exists()
        method, _, path = row["key"].partition(" ")
        assert row["contract_id"] == derive.derive_contract_id(method, path)


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
    candidate: str,
) -> None:
    assert ids.documented_contract_ids(f"`{candidate}`") == {candidate}


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
def test_contract_id_language_rejects_near_misses(candidate: str) -> None:
    assert ids.documented_contract_ids(f"`{candidate}`") == frozenset()


def test_contract_ids_are_extracted_from_prose() -> None:
    """The document is prose plus tables; the ID is picked out of either."""
    text = "The route `management.agents.read.v1` is documented; see also v1 (not an ID)."
    assert ids.documented_contract_ids(text) == {"management.agents.read.v1"}


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


def _doc_line(contract_id: str, key: str, stability: str) -> str:
    method, _, path = key.partition(" ")
    return f"| `{contract_id}` | `{method} {path}` | {stability} |"


def test_contract_document_table_matches_the_registry() -> None:
    doc = model.RegistryPaths.doc.read_text(encoding="utf-8")
    registry = json.loads(model.RegistryPaths.registry.read_text(encoding="utf-8"))
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


def test_document_comparison_tolerates_a_reorder() -> None:
    rows = [
        route_row(RowSpec("GET", "/v1/agents")),
        route_row(RowSpec("POST", "/v1/agents")),
        route_row(RowSpec("DELETE", "/v1/agents/{agent_id}")),
    ]
    documented = [(row["contract_id"], row["key"], row["stability"]) for row in rows]
    assert _doc_mismatches(list(reversed(documented)), rows) == []


def test_document_with_a_stale_contract_id_fails() -> None:
    row = route_row(RowSpec("GET", "/v1/agents"))
    documented = _documented_rows(
        _doc_line(row["contract_id"], row["key"], row["stability"])
        + "\n"
        + _doc_line("management.ghosts.read.v1", "GET /v1/ghosts", "stable")
    )
    assert _doc_mismatches(documented, [row]) == [
        "stale-doc-row: management.ghosts.read.v1 is documented but not registered"
    ]


def test_document_missing_a_contract_id_fails() -> None:
    row = route_row(RowSpec("GET", "/v1/agents"))
    assert _doc_mismatches(_documented_rows(""), [row]) == [
        f"missing-doc-row: {row['contract_id']} is registered but not documented"
    ]


def test_document_with_a_wrong_stability_fails() -> None:
    row = route_row(RowSpec("GET", "/v1/agents"))
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
def test_derivation_rule_is_mechanical(method: str, path: str, expected: str) -> None:
    assert derive.derive_contract_id(method, path) == expected


@pytest.mark.parametrize(
    ("name", "expected"),
    [
        ("ValidateToken", "validate-token"),
        ("BeginTotpEnrollment", "begin-totp-enrollment"),
        ("AssembleContext", "assemble-context"),
        ("Ping", "ping"),
        ("XMLHttpRequest", "xml-http-request"),
        ("HTTPRequest", "http-request"),
        ("AABc", "aa-bc"),
        ("ABCDEFGHIJKLMNOPQRSTUVWXYZab", "abcdefghijklmnopqrstuvwxy-zab"),
        ("A" * 64 + "Bc", "a" * 64 + "-bc"),
    ],
)
def test_kebab_boundaries_are_acronym_safe(name: str, expected: str) -> None:
    """The accepted forms are pinned, including the long-acronym case the rule must survive.

    The rule is a single character plus a fixed-width lookahead per boundary, so a name
    with a long run of capitals is linear work. The previous ``([A-Z]+)([A-Z][a-z])``
    form matched the same strings but backtracked over that run at every position.
    """
    assert derive._kebab(name) == expected


@pytest.mark.parametrize(
    ("key", "expected"),
    [
        ("ibex.auth.v1.AuthService.ValidateToken", "grpc.auth.validate-token.v1"),
        ("ibex.memory.v1.MemoryService.GetMemory", "grpc.memory.get-memory.v1"),
        (
            "ibex.context.v1.ContextAssemblyService.AssembleContext",
            "grpc.context.assemble-context.v1",
        ),
        ("ibex.auth.v1.ValidateToken", "grpc.auth.validate-token.v1"),
        ("nonsense", ""),
        ("a.b", ""),
        ("", ""),
    ],
    ids=["auth", "memory", "context", "no-service-segment", "one-segment", "two-segments", "empty"],
)
def test_grpc_contract_id_accepts_and_rejects_the_documented_forms(key: str, expected: str) -> None:
    """A derived ID is accepted exactly for the documented key forms and empty otherwise."""
    assert derive.grpc_contract_id(key) == expected
    assert derive.is_valid_contract_id(expected) is bool(expected)


@pytest.mark.parametrize(
    ("server", "tool", "expected"),
    [
        ("ibex-mcp-operator", "budget.get", "mcp.operator.budget-get.v1"),
        ("ibex-mcp-memory", "search_memory", "mcp.memory.search-memory.v1"),
        ("operator", "budget.get", "mcp.operator.budget-get.v1"),
        ("", "budget.get", ""),
        ("ibex-mcp-operator", "", ""),
    ],
    ids=["operator", "memory", "unprefixed-server", "no-server", "no-tool"],
)
def test_mcp_contract_id_accepts_and_rejects_the_documented_forms(
    server: str, tool: str, expected: str
) -> None:
    assert derive.mcp_contract_id(server, tool) == expected
    assert derive.is_valid_contract_id(expected) is bool(expected)


def test_synthetic_workspace_baseline_passes(tmp_path: Path, registry_check: ModuleType) -> None:
    paths = workspace(tmp_path, [("GET", "/v1/agents")])
    assert registry_check.check(paths) == []


def test_missing_mounted_route_fails(tmp_path: Path, registry_check: ModuleType) -> None:
    paths = workspace(
        tmp_path,
        [("GET", "/v1/agents"), ("POST", "/v1/agents")],
        WorkspaceSpec(rows=[route_row(RowSpec("GET", "/v1/agents"))]),
    )
    failures = registry_check.check(paths)
    assert any(
        failure.startswith("missing-registration: POST /v1/agents ")
        and "management.agents.create.v1" in failure
        for failure in failures
    )


def test_stale_key_fails(tmp_path: Path, registry_check: ModuleType) -> None:
    paths = workspace(
        tmp_path,
        [("GET", "/v1/agents")],
        WorkspaceSpec(
            rows=[
                route_row(RowSpec("GET", "/v1/agents")),
                route_row(RowSpec("GET", "/v1/ghosts")),
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
    row = route_row(RowSpec("GET", "/v1/agents"))
    paths = workspace(
        tmp_path,
        [("GET", "/v1/agents")],
        WorkspaceSpec(rows=[row], doc_ids=[]),
    )
    failures = registry_check.check(paths)
    assert any(
        failure.startswith(f"undocumented-contract: {row['contract_id']} ") for failure in failures
    )
    # The message names the document actually checked, not a hard-coded default.
    assert any(paths.doc.as_posix() in failure for failure in failures)


def test_invented_contract_id_fails(tmp_path: Path, registry_check: ModuleType) -> None:
    row = route_row(RowSpec("GET", "/v1/agents"))
    row["contract_id"] = "management.agents.invented.v1"
    failures = checked_rows(
        tmp_path,
        WorkspaceSpec(rows=[row], doc_ids=["management.agents.invented.v1"]),
    )
    assert any(failure.startswith("contract-id-mismatch: GET /v1/agents ") for failure in failures)


@pytest.mark.parametrize(
    "value",
    [None, 7, ["api"], {"owner": "api"}],
    ids=["null", "number", "list", "object"],
)
def test_a_required_field_that_is_not_a_string_fails(tmp_path: Path, value: object) -> None:
    """Presence is not validity: a value that is not a string is as unusable as an empty one."""
    row: dict[str, object] = {**route_row(RowSpec("GET", "/v1/agents")), "owner": value}
    failures = checked_rows(tmp_path, WorkspaceSpec(rows=[row]))
    assert f"invalid-field: GET /v1/agents.owner must be a string, not {value!r}" in failures, (
        failures
    )


def test_an_empty_required_field_fails(tmp_path: Path, registry_check: ModuleType) -> None:
    """The empty string is reported as empty, not as a type error."""
    row = route_row(RowSpec("GET", "/v1/agents", owner=""))
    failures = checked_rows(tmp_path, WorkspaceSpec(rows=[row]))
    assert "empty-field: GET /v1/agents has empty owner" in failures, failures


def test_unregistered_status_fails(tmp_path: Path, registry_check: ModuleType) -> None:
    row = route_row(RowSpec("GET", "/v1/agents", status="unregistered"))
    failures = checked_rows(tmp_path, WorkspaceSpec(rows=[row]))
    assert any(failure.startswith("unregistered: GET /v1/agents ") for failure in failures)


def test_unknown_stability_fails(tmp_path: Path, registry_check: ModuleType) -> None:
    row = route_row(RowSpec("GET", "/v1/agents", stability="experimental"))
    failures = checked_rows(tmp_path, WorkspaceSpec(rows=[row]))
    assert any(
        failure.startswith("unknown-enum: GET /v1/agents has stability ") for failure in failures
    )


def test_duplicate_key_fails(tmp_path: Path, registry_check: ModuleType) -> None:
    row = route_row(RowSpec("GET", "/v1/agents"))
    failures = checked_rows(tmp_path, WorkspaceSpec(rows=[row, dict(row)]))
    assert any(failure.startswith("duplicate-key: GET /v1/agents ") for failure in failures)


def test_unknown_schema_fails(tmp_path: Path, registry_check: ModuleType) -> None:
    """The registry declares its own schema version; a different one is not read as this format."""
    paths, registry = workspace_with_registry(tmp_path)
    registry["schema"] = "ibex.contract-registry.v3"
    save_registry(paths, registry)
    assert registry_check.check(paths) == [
        (f"unknown-enum: registry schema is 'ibex.contract-registry.v3'; expected {model.SCHEMA!r}")
    ]


def test_unsorted_registry_names_the_actual_and_expected_key(
    tmp_path: Path, registry_check: ModuleType
) -> None:
    """The message must say what the row is and what belongs in that position, in that order."""
    paths = workspace(tmp_path, [("GET", "/v1/agents"), ("POST", "/v1/agents")])
    registry = json.loads(paths.registry.read_text(encoding="utf-8"))
    registry["routes"] = list(reversed(registry["routes"]))
    save_registry(paths, registry)

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
    assert derive.derive_contract_id("GET", activate) == collision
    assert derive.derive_contract_id("POST", activate) == collision

    paths = workspace(tmp_path, [("GET", activate), ("POST", activate)])
    failures = registry_check.check(paths)
    assert len(failures) == 1, failures
    message = failures[0]
    assert message.startswith(f"duplicate-contract: {collision} is claimed by ")
    assert f"GET {activate}" in message
    assert f"POST {activate}" in message

    committed = json.loads(model.RegistryPaths.registry.read_text(encoding="utf-8"))
    rows = committed["routes"]
    # Pin key -> contract ID, not the row count, so legitimate route additions
    # cost no test edit while a rewritten existing ID fails with a readable diff.
    by_key = {row["key"]: row["contract_id"] for row in rows}
    assert len(by_key) == len(rows)
    assert {key: by_key.get(key) for key in _PINNED_CONTRACT_IDS} == _PINNED_CONTRACT_IDS
    assert len({row["contract_id"] for row in rows}) == len(rows)
    assert len(rows) >= len(_PINNED_CONTRACT_IDS)


@pytest.mark.parametrize(
    ("field", "expected"),
    [
        ("grpc_methods", 'missing-field: registry needs a "grpc_methods" array'),
        ("mcp_tools", 'missing-field: registry needs an "mcp_tools" array'),
    ],
)
def test_required_registry_arrays(
    tmp_path: Path, registry_check: ModuleType, field: str, expected: str
) -> None:
    """Both new arrays are required: a v2 file without one is not read as complete."""
    paths, registry = workspace_with_registry(tmp_path)
    registry.pop(field)
    save_registry(paths, registry)
    assert registry_check.check(paths) == [expected]


def test_scaffold_row_invents_nothing() -> None:
    row = write.scaffold_row("GET", "/v1/agents", ROUTER_SOURCE)
    assert row["owner"] == model.SCAFFOLD_OWNER
    assert row["stability"] == model.SCAFFOLD_STABILITY == "internal"
    assert row["status"] == "unregistered"
    assert row["contract_id"] == "management.agents.read.v1"
    assert row["evidence"] == ROUTER_SOURCE


def test_flipping_status_only_does_not_launder_a_scaffold(
    tmp_path: Path, registry_check: ModuleType
) -> None:
    row = write.scaffold_row("GET", "/v1/agents", ROUTER_SOURCE)
    row["status"] = "shipped"
    paths = workspace(tmp_path, [("GET", "/v1/agents")], WorkspaceSpec(rows=[row]))

    failures = registry_check.check(paths)
    assert any(failure.startswith("unassigned-owner: GET /v1/agents ") for failure in failures), (
        failures
    )

    row["owner"] = "api"
    row["stability"] = "stable"
    write_registry_rows(paths, [row])
    assert registry_check.check(paths) == []


def test_missing_evidence_path_fails_until_the_file_exists(
    tmp_path: Path, registry_check: ModuleType
) -> None:
    row = route_row(RowSpec("GET", "/v1/agents", evidence="services/api/app/nowhere.py"))
    paths = workspace(tmp_path, [("GET", "/v1/agents")], WorkspaceSpec(rows=[row]))
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


def _evidence_failure_for(tmp_path: Path, evidence: str) -> str:
    """Check a single row citing ``evidence`` and return its one missing-evidence line."""
    row = route_row(RowSpec("GET", "/v1/agents", evidence=evidence))
    paths = workspace(tmp_path, [("GET", "/v1/agents")], WorkspaceSpec(rows=[row]))
    failures = [
        failure
        for failure in cli.check(paths)
        if failure.startswith("missing-evidence: GET /v1/agents ")
    ]
    assert len(failures) == 1, failures
    return failures[0]


def test_evidence_absolute_path_outside_the_repository_fails(tmp_path: Path) -> None:
    """`exists()` alone accepted any host file; the citation must stay in the tree."""
    outside = Path("/etc/hostname")
    if not outside.is_file():
        pytest.skip("/etc/hostname is not a file on this platform")
    failure = _evidence_failure_for(tmp_path, outside.as_posix())
    assert outside.as_posix() in failure
    assert "resolves outside" in failure


def test_evidence_directory_fails(tmp_path: Path) -> None:
    """`services/api/app` exists but is a directory, so it cites no code."""
    failure = _evidence_failure_for(tmp_path, "services/api/app")
    assert (tmp_path / "services/api/app").is_dir()
    assert "is not a file" in failure
    assert "directory" in failure


def test_evidence_parent_escape_fails(tmp_path: Path) -> None:
    """A `../` path that exists outside the root still fails containment."""
    escaped = tmp_path.parent / f"{tmp_path.name}-escaped-evidence.md"
    escaped.write_text("", encoding="utf-8")
    failure = _evidence_failure_for(tmp_path, f"../{escaped.name}")
    assert "resolves outside" in failure


def test_evidence_symlink_escaping_the_root_fails(tmp_path: Path) -> None:
    """The symlink exists, so only resolution-based containment can reject it."""
    outside = tmp_path.parent / f"{tmp_path.name}-outside-evidence.md"
    outside.write_text("", encoding="utf-8")
    link = tmp_path / "linked-evidence.md"
    try:
        link.symlink_to(outside)
    except (OSError, NotImplementedError):
        pytest.skip("this platform does not allow creating symlinks")
    assert link.exists()
    failure = _evidence_failure_for(tmp_path, link.name)
    assert "resolves outside" in failure


def test_evidence_symlink_inside_the_root_is_accepted(tmp_path: Path) -> None:
    """Containment is the rule, not "reject every symlink"."""
    link = tmp_path / "linked-evidence.md"
    row = route_row(RowSpec("GET", "/v1/agents", evidence=link.name))
    paths = workspace(tmp_path, [("GET", "/v1/agents")], WorkspaceSpec(rows=[row]))
    try:
        link.symlink_to(tmp_path / ROUTER_SOURCE)
    except (OSError, NotImplementedError):
        pytest.skip("this platform does not allow creating symlinks")
    assert cli.check(paths) == []


def test_write_scaffolds_unregistered_rows_and_leaves_the_gate_red(
    tmp_path: Path, registry_check: ModuleType
) -> None:
    paths = workspace(
        tmp_path,
        [("GET", "/v1/agents"), ("POST", "/v1/agents")],
        WorkspaceSpec(rows=[route_row(RowSpec("GET", "/v1/agents"))]),
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
    assert added[0]["owner"] == model.SCAFFOLD_OWNER
    assert added[0]["stability"] == model.SCAFFOLD_STABILITY
    assert added[0]["contract_id"] == "management.agents.create.v1"

    failures = registry_check.check(paths)
    assert any(failure.startswith("unregistered: POST /v1/agents ") for failure in failures)
    assert any(failure.startswith("unassigned-owner: POST /v1/agents ") for failure in failures)


def test_write_is_atomic(
    tmp_path: Path, registry_check: ModuleType, monkeypatch: pytest.MonkeyPatch
) -> None:
    paths = workspace(
        tmp_path,
        [("GET", "/v1/agents"), ("POST", "/v1/agents")],
        WorkspaceSpec(rows=[route_row(RowSpec("GET", "/v1/agents"))]),
    )
    before = paths.registry.read_text(encoding="utf-8")
    real_replace = write.os.replace

    def _interrupted(src: object, dst: object, *args: object, **kwargs: object) -> None:
        if Path(str(dst)) == paths.registry:
            raise OSError("simulated interruption")
        real_replace(src, dst, *args, **kwargs)

    monkeypatch.setattr(write.os, "replace", _interrupted)
    with pytest.raises(OSError):
        cli.scaffold(paths)

    assert paths.registry.read_text(encoding="utf-8") == before
    assert sorted(path.name for path in tmp_path.glob("*.tmp")) == []
