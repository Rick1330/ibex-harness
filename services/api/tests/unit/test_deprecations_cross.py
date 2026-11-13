"""Unit tests for the cross-surface deprecation checks (W5.4).

A ``rest`` entry resolves against ``contracts/rest-route-registry.json`` and an
``mcp`` entry against its server's committed ``mcp_tools.json``, so these tests pin
the failure a phantom contract, a phantom tool, an unknown server, a wrong server,
and a contradicted class each produce. The registry loader is also pinned: a
duplicate row is a contradiction it refuses to resolve by keeping the last one.

The per-entry field rules live in ``test_deprecations.py`` and the proxy path rules
in ``test_deprecations_paths.py``; the builders they all share are in
``deprecations_test_support.py``.
"""

from __future__ import annotations

from datetime import date
from pathlib import Path

import pytest

from tests.unit.deprecations_test_support import (
    GRPC_CONTRACT,
    REST_CONTRACT,
    TODAY,
    WorkspaceSpec,
    append_route,
    checked,
    cli,
    entry,
    grpc_entry,
    mcp_entry,
    workspace,
)


def test_unknown_contract_id_fails(tmp_path: Path) -> None:
    """A deprecation of a contract the REST registry does not contain is a phantom."""
    failures = checked(tmp_path, [entry(contract_id="management.ghosts.read.v1")])
    assert len(failures) == 1, failures
    assert failures[0].startswith(
        "unknown-contract: dep.agents.read deprecates management.ghosts.read.v1"
    )
    assert "rest-route-registry.json" in failures[0]


def test_registry_stability_mismatch_fails(tmp_path: Path) -> None:
    paths = workspace(tmp_path, [entry()], WorkspaceSpec(rest_stability="beta"))
    failures = cli.check(paths, today=TODAY)
    assert len(failures) == 1, failures
    assert failures[0].startswith("stability-mismatch: dep.agents.read records 'stable' ")
    assert "records 'beta'" in failures[0]


def test_duplicate_registry_row_fails(tmp_path: Path) -> None:
    """Last-wins would let a record pick whichever stability makes its window pass."""
    paths = workspace(tmp_path, [entry()], WorkspaceSpec(rest_stability="beta"))
    append_route(tmp_path, stability="stable")
    failures = cli.check(paths, today=TODAY)
    assert len(failures) == 1, failures
    assert failures[0].startswith("duplicate-registry-row: ")
    assert f"lists {REST_CONTRACT!r} at routes[0] and routes[1]" in failures[0]


def test_mcp_deprecation_passes_and_unknown_tool_fails(tmp_path: Path) -> None:
    valid = mcp_entry()
    assert checked(tmp_path, [valid]) == []

    missing = mcp_entry(tool="budget.delete")
    failures = checked(tmp_path, [missing])
    assert len(failures) == 1, failures
    assert failures[0].startswith("unknown-tool: dep.agents.read deprecates tool 'budget.delete'")
    assert "mcp-operator/mcp_tools.json" in failures[0]


def test_an_entry_outliving_its_tool_is_a_phantom_whatever_its_window_says(
    tmp_path: Path,
) -> None:
    """A completed removal is the tool *and* its entry gone in one change, so this is never it.

    ``packages/mcp_tool_descriptors`` reads the same definition from the other side: a
    removal is authorised by the entry that covered the tool at the base ref, which is
    the entry this check stops requiring once the tool is gone. A tool that never
    existed has no such entry and is reported here, never as a completed removal.
    """
    failures = checked(tmp_path, [mcp_entry(tool="budget.delete")], today=date(2027, 1, 1))
    assert any(
        failure.startswith("unknown-tool: dep.agents.read deprecates tool 'budget.delete'")
        for failure in failures
    ), failures


def test_mcp_stability_must_match_the_tool_descriptor(tmp_path: Path) -> None:
    """The descriptor's class sets the window, so a `stable` claim on a beta tool cannot buy 180 days."""
    failures = checked(tmp_path, [mcp_entry(stability="stable")])
    assert len(failures) == 1, failures
    assert failures[0].startswith("stability-mismatch: dep.agents.read records 'stable' ")
    assert "records 'beta' for tool 'budget.get'" in failures[0]
    assert "mcp-operator/mcp_tools.json" in failures[0]


def test_mcp_stable_tool_accepts_a_stable_entry(tmp_path: Path) -> None:
    """A stable tool's descriptor is what makes the stable class and its 180-day window valid."""
    spec = WorkspaceSpec(tools={"operator": {"budget.get": "stable"}, "memory": {}})
    paths = workspace(tmp_path, [mcp_entry(stability="stable")], spec)
    assert cli.check(paths, today=TODAY) == []


def test_mcp_tool_on_the_wrong_server_fails(tmp_path: Path) -> None:
    """The named server's descriptor is the registry checked, not any server's."""
    failures = checked(tmp_path, [mcp_entry(server="memory")])
    assert len(failures) == 1, failures
    assert "unknown-tool: dep.agents.read deprecates tool 'budget.get'" in failures[0]
    assert "mcp-memory/mcp_tools.json" in failures[0]


def test_unknown_mcp_server_fails(tmp_path: Path) -> None:
    failures = checked(tmp_path, [mcp_entry(server="worker")])
    assert len(failures) == 1, failures
    assert failures[0].startswith("unknown-server: dep.agents.read names server 'worker'")
    assert "['memory', 'operator']" in failures[0]


def test_grpc_contract_id_must_resolve_against_a_method_row(tmp_path: Path) -> None:
    """A gRPC entry resolves against ``grpc_methods``, the same way a REST one resolves."""
    failures = checked(tmp_path, [grpc_entry(contract_id="grpc.ghost.missing.v1")])
    assert len(failures) == 1, failures
    assert failures[0].startswith(
        "unknown-contract: dep.agents.read deprecates grpc.ghost.missing.v1"
    )
    assert "rest-route-registry.json" in failures[0]


def test_grpc_stability_must_match_the_registered_method(tmp_path: Path) -> None:
    """The registry row's class sets the window, so a ``beta`` claim cannot buy 180 days."""
    paths = workspace(
        tmp_path, [grpc_entry(stability="beta")], WorkspaceSpec(grpc_stability="stable")
    )
    failures = cli.check(paths, today=TODAY)
    assert len(failures) == 1, failures
    assert failures[0].startswith("stability-mismatch: dep.agents.read records 'beta' ")
    assert "records 'stable'" in failures[0]
    assert GRPC_CONTRACT in failures[0]


def test_grpc_stable_method_accepts_a_stable_entry(tmp_path: Path) -> None:
    """A resolved contract with the recorded class is the state the check is meant to pass."""
    paths = workspace(tmp_path, [grpc_entry(stability="stable")])
    assert cli.check(paths, today=TODAY) == []


def test_a_relative_registry_path_is_read_from_the_working_directory(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The gRPC rows are read from the path the run loaded, not from a label.

    ``rest_label`` is how a failure names the registry, and it is relative to the
    repository root when the registry is inside it; a relative ``--rest-registry`` is
    relative to the caller's working directory. Rebuilding a path from the label would
    resolve against the repository root and read the wrong file, so the context
    carries the loaded path and this run names the registry from outside the
    repository.
    """
    absolute = workspace(tmp_path, [grpc_entry()])
    monkeypatch.chdir(tmp_path)
    relative = cli.DeprecationPaths(
        record=absolute.record,
        rest_registry=absolute.rest_registry.relative_to(tmp_path),
        mcp_root=absolute.mcp_root,
        root=absolute.root,
    )

    assert cli.check(relative, today=TODAY) == []
