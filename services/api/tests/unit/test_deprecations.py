"""Unit tests for the deprecation record check (W5.4).

The first tests assert the committed record against the committed registries. The
rest build a synthetic workspace in ``tmp_path`` so each failure mode is isolated;
none of them touch PostgreSQL, the app, or the tree.

The record is the notice of record, so the tests pin the two properties the gate
exists for: a window shorter than 180 days (stable) or 31 days (beta) cannot be
recorded, and a deprecation cannot name a contract, tool, or server that the
committed registries do not contain.
"""

from __future__ import annotations

import importlib.util
import json
import sys
from dataclasses import dataclass, field
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from types import ModuleType
from typing import Any

import pytest

_SCRIPT = Path(__file__).resolve().parents[2] / "scripts" / "check_deprecations.py"

_REST_CONTRACT = "management.agents.read.v1"
_EVIDENCE = "engineering/architecture-v2/16-compatibility-and-versioning.md"
_MCP_TOOLS = {"operator": ["budget.get"], "memory": ["get_memory_lineage"]}
_MCP_TOOL = "budget.get"
_MCP_SERVER = "operator"

_NOTICE = date(2026, 1, 1)
_TODAY = date(2026, 1, 15)


def _sunset(days: int) -> str:
    return (_NOTICE + timedelta(days=days)).isoformat()


@pytest.fixture(scope="module")
def deprecations() -> ModuleType:
    spec = importlib.util.spec_from_file_location("check_deprecations", _SCRIPT)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


@dataclass(frozen=True)
class _WorkspaceSpec:
    """Overrides for the synthetic registry workspace."""

    rest_stability: str = "stable"
    tools: dict[str, list[str]] = field(default_factory=lambda: dict(_MCP_TOOLS))


def _entry(**overrides: Any) -> dict[str, Any]:
    """A valid announced REST deprecation with a 180-day window."""
    entry: dict[str, Any] = {
        "id": "dep.agents.read",
        "surface": "rest",
        "contract_id": _REST_CONTRACT,
        "successor": "management.agents.v2",
        "stability": "stable",
        "notice_date": _NOTICE.isoformat(),
        "sunset_date": _sunset(180),
        "status": "announced",
        "headers_implemented": True,
        "evidence": _EVIDENCE,
    }
    entry.update(overrides)
    return {key: value for key, value in entry.items() if value is not None}


def _entry_stability(entries: list[dict[str, Any]]) -> str:
    """Default the registry row to the recorded class, so a window test needs no spec."""
    if not entries:
        return "stable"
    return str(entries[0].get("stability", "stable"))


def _workspace(
    tmp_path: Path,
    module: ModuleType,
    entries: list[dict[str, Any]],
    spec: _WorkspaceSpec | None = None,
) -> object:
    options = spec or _WorkspaceSpec(rest_stability=_entry_stability(entries))
    _write_registries(tmp_path, options)
    evidence = tmp_path / _EVIDENCE
    evidence.parent.mkdir(parents=True, exist_ok=True)
    evidence.write_text("", encoding="utf-8")
    record = tmp_path / "deprecations.json"
    record.write_text(
        json.dumps({"schema": module.SCHEMA, "entries": entries}, indent=2) + "\n",
        encoding="utf-8",
    )
    return module.DeprecationPaths(
        record=record,
        rest_registry=tmp_path / "rest-route-registry.json",
        mcp_root=tmp_path / "services",
        root=tmp_path,
    )


def _write_registries(tmp_path: Path, spec: _WorkspaceSpec) -> None:
    rest_row = {
        "key": "GET /v1/agents",
        "contract_id": _REST_CONTRACT,
        "owner": "api",
        "stability": spec.rest_stability,
        "status": "shipped",
        "evidence": "services/api/app/routers/agents.py",
    }
    registry = {"schema": "ibex.contract-registry.v1", "routes": [rest_row]}
    (tmp_path / "rest-route-registry.json").write_text(
        json.dumps(registry, indent=2) + "\n", encoding="utf-8"
    )
    for server, names in spec.tools.items():
        server_dir = tmp_path / "services" / f"mcp-{server}"
        server_dir.mkdir(parents=True, exist_ok=True)
        payload = {"tools": [{"name": name, "stability": "beta"} for name in names]}
        (server_dir / "mcp_tools.json").write_text(
            json.dumps(payload, indent=2) + "\n", encoding="utf-8"
        )


def _append_route(tmp_path: Path, stability: str) -> None:
    """Append a second row for the same contract, as a contradictory registry would."""
    path = tmp_path / "rest-route-registry.json"
    registry = json.loads(path.read_text(encoding="utf-8"))
    registry["routes"].append(
        {
            "key": "GET /v1/agents",
            "contract_id": _REST_CONTRACT,
            "owner": "api",
            "stability": stability,
            "status": "shipped",
            "evidence": "services/api/app/routers/agents.py",
        }
    )
    path.write_text(json.dumps(registry, indent=2) + "\n", encoding="utf-8")


def _argv(paths: Any) -> list[str]:
    return [
        "--check",
        "--record",
        str(paths.record),
        "--rest-registry",
        str(paths.rest_registry),
        "--mcp-root",
        str(paths.mcp_root),
        "--root",
        str(paths.root),
    ]


def _check(
    tmp_path: Path,
    module: ModuleType,
    entries: list[dict[str, Any]],
    *,
    today: date = _TODAY,
) -> list[str]:
    return module.check(_workspace(tmp_path, module, entries), today=today)


def test_committed_record_is_empty_and_valid(deprecations: ModuleType) -> None:
    """Empty is the correct 1.0 state: nothing is deprecated, and the check proves it."""
    record = json.loads(deprecations.DeprecationPaths.record.read_text(encoding="utf-8"))
    assert record["schema"] == deprecations.SCHEMA
    assert record["entries"] == []
    assert deprecations.check() == []


def test_check_flag_is_accepted_and_passes_on_the_committed_record(
    deprecations: ModuleType, capsys: pytest.CaptureFixture[str]
) -> None:
    """`--check` names the default and only mode; it must not be an unknown argument."""
    assert deprecations.main(["--check"]) == 0
    captured = capsys.readouterr()
    assert "deprecation record is valid" in captured.out
    assert "empty entries array means nothing is deprecated" in captured.out


def test_announced_rest_deprecation_with_a_full_window_passes(
    tmp_path: Path, deprecations: ModuleType
) -> None:
    assert _check(tmp_path, deprecations, [_entry()]) == []


@pytest.mark.parametrize(
    "case",
    [
        ("stable", 180, True),
        ("stable", 179, False),
        ("beta", 31, True),
        ("beta", 30, False),
    ],
    ids=["stable-180", "stable-179", "beta-31", "beta-30"],
)
def test_window_must_meet_the_class_minimum(
    tmp_path: Path, deprecations: ModuleType, case: tuple[str, int, bool]
) -> None:
    """180 days for stable and 31 days for beta, and the boundary day itself passes."""
    stability, days, valid = case
    failures = _check(
        tmp_path,
        deprecations,
        [_entry(stability=stability, sunset_date=_sunset(days))],
    )
    if valid:
        assert failures == []
        return
    assert len(failures) == 1, failures
    minimum = deprecations.WINDOW_DAYS[stability]
    assert failures[0].startswith(f"window-too-short: dep.agents.read is {stability},")
    assert f"at least {minimum} days" in failures[0]
    assert f"this window is {days} day(s)" in failures[0]


def test_missing_record_fails(tmp_path: Path, deprecations: ModuleType) -> None:
    paths = _workspace(tmp_path, deprecations, [])
    paths.record.unlink()
    assert deprecations.check(paths) == [f"missing-record: {paths.record} does not exist"]


def test_unknown_contract_id_fails(tmp_path: Path, deprecations: ModuleType) -> None:
    """A deprecation of a contract the REST registry does not contain is a phantom."""
    failures = _check(tmp_path, deprecations, [_entry(contract_id="management.ghosts.read.v1")])
    assert len(failures) == 1, failures
    assert failures[0].startswith(
        "unknown-contract: dep.agents.read deprecates management.ghosts.read.v1"
    )
    assert "rest-route-registry.json" in failures[0]


def test_registry_stability_mismatch_fails(tmp_path: Path, deprecations: ModuleType) -> None:
    paths = _workspace(tmp_path, deprecations, [_entry()], _WorkspaceSpec(rest_stability="beta"))
    failures = deprecations.check(paths, today=_TODAY)
    assert len(failures) == 1, failures
    assert failures[0].startswith("stability-mismatch: dep.agents.read records 'stable' ")
    assert "records 'beta'" in failures[0]


def test_duplicate_registry_row_fails(tmp_path: Path, deprecations: ModuleType) -> None:
    """Last-wins would let a record pick whichever stability makes its window pass."""
    paths = _workspace(tmp_path, deprecations, [_entry()], _WorkspaceSpec(rest_stability="beta"))
    _append_route(tmp_path, stability="stable")
    failures = deprecations.check(paths, today=_TODAY)
    assert len(failures) == 1, failures
    assert failures[0].startswith("duplicate-registry-row: ")
    assert f"lists {_REST_CONTRACT!r} at routes[0] and routes[1]" in failures[0]


def test_mcp_deprecation_passes_and_unknown_tool_fails(
    tmp_path: Path, deprecations: ModuleType
) -> None:
    valid = _entry(surface="mcp", contract_id=None, tool=_MCP_TOOL, server=_MCP_SERVER)
    assert _check(tmp_path, deprecations, [valid]) == []

    missing = _entry(surface="mcp", contract_id=None, tool="budget.delete", server=_MCP_SERVER)
    failures = _check(tmp_path, deprecations, [missing])
    assert len(failures) == 1, failures
    assert failures[0].startswith("unknown-tool: dep.agents.read deprecates tool 'budget.delete'")
    assert "mcp-operator/mcp_tools.json" in failures[0]


def test_mcp_tool_on_the_wrong_server_fails(tmp_path: Path, deprecations: ModuleType) -> None:
    """The named server's descriptor is the registry checked, not any server's."""
    entry = _entry(surface="mcp", contract_id=None, tool=_MCP_TOOL, server="memory")
    failures = _check(tmp_path, deprecations, [entry])
    assert len(failures) == 1, failures
    assert "unknown-tool: dep.agents.read deprecates tool 'budget.get'" in failures[0]
    assert "mcp-memory/mcp_tools.json" in failures[0]


def test_unknown_mcp_server_fails(tmp_path: Path, deprecations: ModuleType) -> None:
    entry = _entry(surface="mcp", contract_id=None, tool=_MCP_TOOL, server="worker")
    failures = _check(tmp_path, deprecations, [entry])
    assert len(failures) == 1, failures
    assert failures[0].startswith("unknown-server: dep.agents.read names server 'worker'")
    assert "['memory', 'operator']" in failures[0]


def test_successor_must_be_named_and_must_differ_from_the_contract(
    tmp_path: Path, deprecations: ModuleType
) -> None:
    failures = _check(tmp_path, deprecations, [_entry(successor=_REST_CONTRACT)])
    assert failures == [
        f"successor-is-self: dep.agents.read names {_REST_CONTRACT!r} as its own successor"
    ]

    empty = _check(tmp_path, deprecations, [_entry(successor="")])
    assert any(
        failure.startswith("empty-field: dep.agents.read has empty successor") for failure in empty
    ), empty


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        (None, "invalid-field: dep.agents.read.successor must be a string, not None"),
        ("   ", "empty-field: dep.agents.read has empty successor"),
    ],
    ids=["null", "whitespace"],
)
def test_successor_must_be_a_non_blank_string(
    tmp_path: Path, deprecations: ModuleType, value: object, expected: str
) -> None:
    """Presence is not validity: `null` and a blank string are not a successor."""
    entry = _entry()
    entry["successor"] = value
    failures = _check(tmp_path, deprecations, [entry])
    assert failures == [expected]


def test_announced_without_headers_fails(tmp_path: Path, deprecations: ModuleType) -> None:
    """A deprecation may not be announced before the headers are implemented."""
    failures = _check(tmp_path, deprecations, [_entry(headers_implemented=False)])
    assert len(failures) == 1, failures
    assert failures[0].startswith("headers-not-implemented: dep.agents.read is announced")


def test_announced_with_missing_evidence_fails(tmp_path: Path, deprecations: ModuleType) -> None:
    failures = _check(
        tmp_path,
        deprecations,
        [_entry(evidence="engineering/architecture-v2/nowhere.md")],
    )
    assert len(failures) == 1, failures
    assert failures[0].startswith("missing-evidence: dep.agents.read cites ")
    assert "nowhere.md" in failures[0]
    assert "does not exist" in failures[0]


def test_evidence_outside_the_workspace_root_fails(
    tmp_path: Path, deprecations: ModuleType
) -> None:
    """A citation that escapes the root is not evidence, even when the file exists."""
    outside = tmp_path.parent / f"{tmp_path.name}-outside.md"
    outside.write_text("", encoding="utf-8")
    try:
        failures = _check(tmp_path, deprecations, [_entry(evidence=f"../{outside.name}")])
    finally:
        outside.unlink()
    assert len(failures) == 1, failures
    assert "resolves outside" in failures[0]


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        (None, "invalid-field: dep.agents.read.evidence must be a string, not None"),
        ("", "empty-field: dep.agents.read has empty evidence"),
    ],
    ids=["null", "empty"],
)
def test_announced_evidence_must_be_a_string(
    tmp_path: Path, deprecations: ModuleType, value: object, expected: str
) -> None:
    """An announced deprecation may not cite `null` as evidence, and `""` does not pass."""
    entry = _entry()
    entry["evidence"] = value
    failures = _check(tmp_path, deprecations, [entry])
    assert failures == [expected]


def test_announced_past_its_sunset_fails(tmp_path: Path, deprecations: ModuleType) -> None:
    late = date(2026, 8, 1)
    failures = _check(tmp_path, deprecations, [_entry()], today=late)
    assert len(failures) == 1, failures
    assert failures[0].startswith("sunset-passed: dep.agents.read is announced")
    assert "withdraw it" in failures[0]


def test_proposed_deprecation_without_headers_or_live_evidence_is_allowed(
    tmp_path: Path, deprecations: ModuleType
) -> None:
    """The implementation gate binds `announced` only; a proposal may precede it."""
    entry = _entry(
        status="proposed",
        headers_implemented=False,
        evidence="engineering/architecture-v2/31-v1-release-plan-2026-11-09.md",
    )
    assert _check(tmp_path, deprecations, [entry], today=date(2026, 8, 1)) == []


@pytest.mark.parametrize(
    "case",
    [
        ("surface", "graphql", "unknown-enum: dep.agents.read has surface 'graphql'"),
        ("surface", [], "unknown-enum: dep.agents.read has surface []"),
        ("stability", "internal", "unknown-enum: dep.agents.read has stability 'internal'"),
        ("status", "retired", "unknown-enum: dep.agents.read has status 'retired'"),
        (
            "headers_implemented",
            "true",
            "invalid-field: dep.agents.read.headers_implemented must be a boolean",
        ),
        ("notice_date", "20260101", "invalid-date: dep.agents.read.notice_date is '20260101'"),
    ],
    ids=["surface", "surface-type", "stability", "status", "headers", "date"],
)
def test_invalid_field_values_fail(
    tmp_path: Path, deprecations: ModuleType, case: tuple[str, object, str]
) -> None:
    field, value, expected = case
    failures = _check(tmp_path, deprecations, [_entry(**{field: value})])
    assert any(failure.startswith(expected) for failure in failures), failures


def test_unknown_field_fails(tmp_path: Path, deprecations: ModuleType) -> None:
    """The schema is closed, so a stray field cannot carry an unvalidated claim."""
    failures = _check(tmp_path, deprecations, [_entry(owner="api")])
    assert failures == ["unknown-field: dep.agents.read has owner"]


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("notice_date", None),
        ("notice_date", 20260101),
        ("sunset_date", None),
        ("sunset_date", [2026, 1, 1]),
    ],
    ids=["notice-null", "notice-int", "sunset-null", "sunset-list"],
)
def test_non_string_date_fails(
    tmp_path: Path, deprecations: ModuleType, field: str, value: object
) -> None:
    """A non-string date cannot be parsed, so the window would silently not be checked."""
    entry = _entry()
    entry[field] = value
    failures = _check(tmp_path, deprecations, [entry])
    assert failures == [f"invalid-date: dep.agents.read.{field} is {value!r}; expected YYYY-MM-DD"]


def test_missing_field_fails(tmp_path: Path, deprecations: ModuleType) -> None:
    entry = _entry()
    del entry["successor"]
    failures = _check(tmp_path, deprecations, [entry])
    assert failures == ["missing-field: dep.agents.read lacks successor"]


def test_unexpected_selector_for_the_surface_fails(
    tmp_path: Path, deprecations: ModuleType
) -> None:
    """`contract_id | tool` is exclusive: an MCP entry carrying `contract_id` is a shape error."""
    entry = _entry(surface="mcp", tool=_MCP_TOOL, server=_MCP_SERVER)
    failures = _check(tmp_path, deprecations, [entry])
    assert failures == ["unknown-field: dep.agents.read has contract_id"]


def test_duplicate_id_fails(tmp_path: Path, deprecations: ModuleType) -> None:
    failures = _check(tmp_path, deprecations, [_entry(), _entry()])
    assert any(
        failure.startswith("duplicate-id: dep.agents.read appears at entries[0] and entries[1]")
        for failure in failures
    ), failures


def test_unsorted_entries_fail(tmp_path: Path, deprecations: ModuleType) -> None:
    entries = [_entry(id="dep.z"), _entry(id="dep.a")]
    failures = _check(tmp_path, deprecations, entries)
    assert failures == [
        "unsorted-record: entries[0] is 'dep.z'; expected 'dep.a' (entries are sorted by id)"
    ]


def test_unknown_schema_fails(tmp_path: Path, deprecations: ModuleType) -> None:
    paths = _workspace(tmp_path, deprecations, [])
    record = json.loads(paths.record.read_text(encoding="utf-8"))
    record["schema"] = "ibex.deprecations.v2"
    paths.record.write_text(json.dumps(record, indent=2) + "\n", encoding="utf-8")
    assert deprecations.check(paths) == [
        (f"unknown-enum: record schema is 'ibex.deprecations.v2'; expected {deprecations.SCHEMA!r}")
    ]


def test_deeply_nested_record_fails_closed(tmp_path: Path, deprecations: ModuleType) -> None:
    """A parse failure is a diagnostic, not an uncaught RecursionError."""
    paths = _workspace(tmp_path, deprecations, [])
    paths.record.write_text("[" * 100_000 + "]" * 100_000, encoding="utf-8")
    failures = deprecations.check(paths)
    assert len(failures) == 1, failures
    assert failures[0].startswith(f"invalid-record: {paths.record}: ")
    assert "nested too deeply" in failures[0]


def _current_entry(days: int) -> dict[str, Any]:
    """An announced entry whose window starts today, so the CLI test never ages out."""
    notice = datetime.now(UTC).date()
    return _entry(
        notice_date=notice.isoformat(),
        sunset_date=(notice + timedelta(days=days)).isoformat(),
    )


def test_main_checks_a_record_in_a_temp_tree(
    tmp_path: Path, deprecations: ModuleType, capsys: pytest.CaptureFixture[str]
) -> None:
    """The CLI takes every input as a path, so the positive case is reproducible."""
    paths = _workspace(tmp_path, deprecations, [_current_entry(180)])
    argv = [
        "--check",
        "--record",
        str(paths.record),
        "--rest-registry",
        str(paths.rest_registry),
        "--mcp-root",
        str(paths.mcp_root),
        "--root",
        str(paths.root),
    ]
    assert deprecations.main(argv) == 0
    assert f"deprecation record is valid: {paths.record}" in capsys.readouterr().out

    _workspace(tmp_path, deprecations, [_current_entry(179)])
    assert deprecations.main(argv) == 1
    assert "window-too-short" in capsys.readouterr().err


def test_empty_record_note_is_conditional(
    tmp_path: Path, deprecations: ModuleType, capsys: pytest.CaptureFixture[str]
) -> None:
    """The note is true only of the empty record; printing it for entries misleads."""
    paths = _workspace(tmp_path, deprecations, [_current_entry(180)])
    argv = _argv(paths)
    assert deprecations.main(argv) == 0
    out = capsys.readouterr().out
    assert f"deprecation record is valid: {paths.record}" in out
    assert "empty entries array means nothing is deprecated" not in out

    _workspace(tmp_path, deprecations, [])
    assert deprecations.main(argv) == 0
    assert "note: an empty entries array means nothing is deprecated" in capsys.readouterr().out
