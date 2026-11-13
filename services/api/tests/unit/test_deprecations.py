"""Unit tests for the committed record and the per-entry deprecation rules (W5.4).

The first tests assert the committed record against the committed registries and run
the CLI over it. The rest build a synthetic workspace in ``tmp_path`` so each
failure mode is isolated; none of them touch PostgreSQL, the app, or the tree.

The record is the notice of record, so the tests pin the properties the gate
exists for: a window shorter than 180 days (stable) or 31 days (beta) cannot be
recorded, the window is measured from the announcement rather than an earlier
plan date, and ``headers_implemented`` is true only where a standard deprecation
header exists (REST and proxy).

The proxy path selector and the duplicate rules live in
``test_deprecations_paths.py``, and the registry cross-checks in
``test_deprecations_cross.py``; the builders they all share are in
``deprecations_test_support.py``.
"""

from __future__ import annotations

import json
from datetime import date, timedelta
from pathlib import Path

import pytest

from tests.unit.deprecations_test_support import (
    MCP_SERVER,
    MCP_TOOL,
    REST_CONTRACT,
    TODAY,
    argv,
    checked,
    cli,
    current_entry,
    entry,
    grpc_entry,
    mcp_entry,
    model,
    proxy_entry,
    sunset,
    workspace,
)


def test_committed_record_is_empty_and_valid() -> None:
    """Empty is the correct 1.0 state: nothing is deprecated, and the check proves it."""
    record = json.loads(cli.DeprecationPaths.record.read_text(encoding="utf-8"))
    assert record["schema"] == cli.SCHEMA
    assert record["entries"] == []
    assert cli.check() == []


def test_check_flag_is_accepted_and_passes_on_the_committed_record(
    capsys: pytest.CaptureFixture[str],
) -> None:
    """`--check` names the default and only mode; it must not be an unknown argument."""
    assert cli.main(["--check"]) == 0
    captured = capsys.readouterr()
    assert "deprecation record is valid" in captured.out
    assert "empty entries array means nothing is deprecated" in captured.out


def test_announced_rest_deprecation_with_a_full_window_passes(tmp_path: Path) -> None:
    assert checked(tmp_path, [entry()]) == []


@pytest.mark.parametrize("surface", ["rest", "grpc"])
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
    tmp_path: Path, surface: str, case: tuple[str, int, bool]
) -> None:
    """180 days for stable and 31 for beta, and the boundary day itself passes.

    The window arithmetic is defined once and exercised on both surfaces that
    resolve against no registry, so a gRPC entry cannot drift to a different rule.
    """
    stability, days, valid = case
    factory = entry if surface == "rest" else grpc_entry
    failures = checked(
        tmp_path,
        [factory(stability=stability, sunset_date=sunset(days))],
    )
    if valid:
        assert failures == []
        return
    assert len(failures) == 1, failures
    minimum = model.WINDOW_DAYS[stability]
    assert failures[0].startswith(f"window-too-short: dep.agents.read is {stability},")
    assert f"at least {minimum} days" in failures[0]
    assert f"this window is {days} day(s)" in failures[0]


def test_missing_record_fails(tmp_path: Path) -> None:
    paths = workspace(tmp_path, [])
    paths.record.unlink()
    assert cli.check(paths) == [f"missing-record: {paths.record} does not exist"]


def test_announced_proxy_entry_without_headers_fails(tmp_path: Path) -> None:
    """The proxy emits only when the entry declares the headers, so an announced one must."""
    failures = checked(tmp_path, [proxy_entry(headers_implemented=False)])
    assert len(failures) == 1, failures
    assert failures[0].startswith("headers-not-implemented: dep.agents.read is announced")


def test_successor_must_be_named_and_must_differ_from_the_contract(tmp_path: Path) -> None:
    failures = checked(tmp_path, [entry(successor=REST_CONTRACT)])
    assert failures == [
        f"successor-is-self: dep.agents.read names {REST_CONTRACT!r} as its own successor"
    ]

    empty = checked(tmp_path, [entry(successor="")])
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
def test_successor_must_be_a_non_blank_string(tmp_path: Path, value: object, expected: str) -> None:
    """Presence is not validity: `null` and a blank string are not a successor."""
    record_entry = entry()
    record_entry["successor"] = value
    failures = checked(tmp_path, [record_entry])
    assert failures == [expected]


def test_announced_without_headers_fails(tmp_path: Path) -> None:
    """A REST deprecation may not be announced before the headers are implemented."""
    failures = checked(tmp_path, [entry(headers_implemented=False)])
    assert len(failures) == 1, failures
    assert failures[0].startswith("headers-not-implemented: dep.agents.read is announced")


@pytest.mark.parametrize("status", ["proposed", "withdrawn"])
def test_unannounced_rest_entry_cannot_claim_deprecation_headers(
    tmp_path: Path, status: str
) -> None:
    """The header flag tracks the announcement: it is false until `announced`, and after a withdrawal."""
    record_entry = entry(status=status, headers_implemented=True, announced_on=None)
    failures = checked(tmp_path, [record_entry])
    assert len(failures) == 1, failures
    assert failures[0].startswith(f"headers-before-announcement: dep.agents.read is {status}")
    assert "headers_implemented must be false until it is announced" in failures[0]
    assert "consumers were never told about" in failures[0]


def test_grpc_and_mcp_cannot_claim_deprecation_headers(tmp_path: Path) -> None:
    """No standard header exists for those surfaces, so the record is the notice of record."""
    for record_entry in (
        grpc_entry(headers_implemented=True),
        mcp_entry(headers_implemented=True),
    ):
        failures = checked(tmp_path, [record_entry])
        assert len(failures) == 1, failures
        assert failures[0].startswith(
            f"headers-not-applicable: dep.agents.read is {record_entry['surface']}, "
        )
        assert "headers_implemented must be false" in failures[0]
        assert "the record is the notice of record" in failures[0]


def test_announced_without_an_announcement_date_fails(tmp_path: Path) -> None:
    """The window is measured from the announcement, so an announced entry must date it."""
    record_entry = entry()
    del record_entry["announced_on"]
    failures = checked(tmp_path, [record_entry])
    assert len(failures) == 1, failures
    assert failures[0].startswith(
        "missing-announcement: dep.agents.read is announced but has no announced_on"
    )
    assert "window is measured from it" in failures[0]


@pytest.mark.parametrize(
    "case",
    [("stable", 180), ("beta", 31)],
    ids=["stable-180", "beta-31"],
)
def test_notice_on_the_announcement_day_meets_the_minimum(
    tmp_path: Path, case: tuple[str, int]
) -> None:
    """When notice and announcement coincide, the boundary day is exactly enough."""
    stability, days = case
    assert checked(tmp_path, [entry(stability=stability, sunset_date=sunset(days))]) == []


def test_window_is_measured_from_the_announcement_not_the_notice(tmp_path: Path) -> None:
    """An early notice cannot buy window time the announcement never gave the consumer."""
    record_entry = entry(
        notice_date="2025-06-01", announced_on="2026-01-01", sunset_date="2026-01-30"
    )
    failures = checked(tmp_path, [record_entry])
    assert len(failures) == 1, failures
    assert failures[0].startswith("window-too-short: dep.agents.read is stable,")
    assert "at least 180 days after announced_on 2026-01-01" in failures[0]
    assert "this window is 29 day(s)" in failures[0]


def test_announced_on_after_today_fails(tmp_path: Path) -> None:
    """A future date is a scheduled edit, not a notice: nobody has been told yet."""
    record_entry = entry(announced_on="2026-12-01", sunset_date="2027-06-01")
    failures = checked(tmp_path, [record_entry])
    assert len(failures) == 1, failures
    assert failures[0].startswith(
        "announcement-in-future: dep.agents.read records announced_on 2026-12-01"
    )
    assert "is after today 2026-01-15" in failures[0]
    assert "consumers have been told" in failures[0]


def test_announced_on_today_passes(tmp_path: Path) -> None:
    """The boundary day is in the past for the purposes of the rule, so it is allowed."""
    record_entry = entry(
        announced_on=TODAY.isoformat(),
        sunset_date=(TODAY + timedelta(days=180)).isoformat(),
    )
    assert checked(tmp_path, [record_entry]) == []


def test_announced_on_before_the_notice_date_fails(tmp_path: Path) -> None:
    """A window cannot start before the deprecation was noticed."""
    failures = checked(tmp_path, [entry(announced_on="2025-12-01")])
    assert failures == [
        (
            "announcement-before-notice: dep.agents.read was announced on 2025-12-01 before its "
            "notice_date 2026-01-01; the window cannot start before the notice"
        )
    ]


@pytest.mark.parametrize("value", [20260101, [2026, 1, 1]], ids=["int", "list"])
def test_non_string_announced_on_fails(tmp_path: Path, value: object) -> None:
    """A non-string announcement date cannot anchor the window, so it is not a date."""
    record_entry = entry()
    record_entry["announced_on"] = value
    failures = checked(tmp_path, [record_entry])
    assert failures == [
        f"invalid-date: dep.agents.read.announced_on is {value!r}; expected YYYY-MM-DD"
    ]


def test_null_announcement_date_is_allowed_before_announcement(tmp_path: Path) -> None:
    """A proposal carries no announcement date, and a null is an absent date, not a wrong one."""
    record_entry = entry(status="proposed", headers_implemented=False)
    record_entry["announced_on"] = None
    assert checked(tmp_path, [record_entry]) == []


@pytest.mark.parametrize("status", ["proposed", "withdrawn"])
def test_announcement_date_is_rejected_before_it_is_announced(tmp_path: Path, status: str) -> None:
    """A proposal or withdrawal cannot claim a date on which consumers were told."""
    failures = checked(tmp_path, [entry(status=status, headers_implemented=False)])
    assert len(failures) == 1, failures
    assert failures[0].startswith(
        f"unexpected-announcement: dep.agents.read is {status}, so announced_on must be absent or null"
    )


def test_announced_grpc_entry_without_headers_passes(tmp_path: Path) -> None:
    """No gRPC header exists, so `false` is the only truthful value and the record is the notice."""
    assert checked(tmp_path, [grpc_entry()]) == []


def test_grpc_entry_without_contract_id_fails(tmp_path: Path) -> None:
    record_entry = grpc_entry()
    del record_entry["contract_id"]
    failures = checked(tmp_path, [record_entry])
    assert failures == ["missing-field: dep.agents.read lacks contract_id"]


def test_grpc_entry_carrying_mcp_selectors_fails(tmp_path: Path) -> None:
    """The selector is exclusive: a gRPC entry names a contract, not a tool on a server."""
    record_entry = grpc_entry(tool=MCP_TOOL, server=MCP_SERVER)
    failures = checked(tmp_path, [record_entry])
    assert failures == ["unknown-field: dep.agents.read has server, tool"]


def test_grpc_contract_id_resolves_against_no_registry(tmp_path: Path) -> None:
    """No gRPC method registry is committed, so the id is not cross-checked; the field set is."""
    unknown = grpc_entry(contract_id="ibex.ghost.v1.GhostService/Missing")
    assert checked(tmp_path, [unknown]) == []


def test_announced_with_missing_evidence_fails(tmp_path: Path) -> None:
    failures = checked(
        tmp_path,
        [entry(evidence="engineering/architecture-v2/nowhere.md")],
    )
    assert len(failures) == 1, failures
    assert failures[0].startswith("missing-evidence: dep.agents.read cites ")
    assert "nowhere.md" in failures[0]
    assert "does not exist" in failures[0]


def test_evidence_outside_the_workspace_root_fails(tmp_path: Path) -> None:
    """A citation that escapes the root is not evidence, even when the file exists."""
    outside = tmp_path.parent / f"{tmp_path.name}-outside.md"
    outside.write_text("", encoding="utf-8")
    try:
        failures = checked(tmp_path, [entry(evidence=f"../{outside.name}")])
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
def test_announced_evidence_must_be_a_string(tmp_path: Path, value: object, expected: str) -> None:
    """An announced deprecation may not cite `null` as evidence, and `""` does not pass."""
    record_entry = entry()
    record_entry["evidence"] = value
    failures = checked(tmp_path, [record_entry])
    assert failures == [expected]


def test_announced_past_its_sunset_fails(tmp_path: Path) -> None:
    late = date(2026, 8, 1)
    failures = checked(tmp_path, [entry()], today=late)
    assert len(failures) == 1, failures
    assert failures[0].startswith("sunset-passed: dep.agents.read is announced")
    assert "withdraw it" in failures[0]


def test_proposed_deprecation_without_headers_or_live_evidence_is_allowed(tmp_path: Path) -> None:
    """The implementation gate binds `announced` only; a proposal may precede it."""
    record_entry = entry(
        status="proposed",
        headers_implemented=False,
        announced_on=None,
        evidence="engineering/architecture-v2/31-v1-release-plan-2026-11-09.md",
    )
    assert checked(tmp_path, [record_entry], today=date(2026, 8, 1)) == []


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
def test_invalid_field_values_fail(tmp_path: Path, case: tuple[str, object, str]) -> None:
    field, value, expected = case
    failures = checked(tmp_path, [entry(**{field: value})])
    assert any(failure.startswith(expected) for failure in failures), failures


def test_non_string_status_is_reported_not_raised(tmp_path: Path) -> None:
    """A malformed status is an enum failure; the dated and header rules must not raise on it."""
    failures = checked(tmp_path, [entry(status=["announced"])])
    assert failures == [
        (
            "unknown-enum: dep.agents.read has status ['announced']; "
            "expected one of ['announced', 'proposed', 'withdrawn']"
        )
    ]


def test_unknown_field_fails(tmp_path: Path) -> None:
    """The schema is closed, so a stray field cannot carry an unvalidated claim."""
    failures = checked(tmp_path, [entry(owner="api")])
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
def test_non_string_date_fails(tmp_path: Path, field: str, value: object) -> None:
    """A non-string date cannot be parsed, so the window would silently not be checked."""
    record_entry = entry()
    record_entry[field] = value
    failures = checked(tmp_path, [record_entry])
    assert failures == [f"invalid-date: dep.agents.read.{field} is {value!r}; expected YYYY-MM-DD"]


def test_missing_field_fails(tmp_path: Path) -> None:
    record_entry = entry()
    del record_entry["successor"]
    failures = checked(tmp_path, [record_entry])
    assert failures == ["missing-field: dep.agents.read lacks successor"]


def test_unexpected_selector_for_the_surface_fails(tmp_path: Path) -> None:
    """`contract_id | tool` is exclusive: an MCP entry carrying `contract_id` is a shape error."""
    record_entry = mcp_entry(contract_id=REST_CONTRACT)
    failures = checked(tmp_path, [record_entry])
    assert failures == ["unknown-field: dep.agents.read has contract_id"]


def test_duplicate_id_fails(tmp_path: Path) -> None:
    failures = checked(tmp_path, [entry(), entry()])
    assert any(
        failure.startswith("duplicate-id: dep.agents.read appears at entries[0] and entries[1]")
        for failure in failures
    ), failures


def test_unsorted_entries_fail(tmp_path: Path) -> None:
    entries = [entry(id="dep.z"), entry(id="dep.a")]
    failures = checked(tmp_path, entries)
    assert failures == [
        "unsorted-record: entries[0] is 'dep.z'; expected 'dep.a' (entries are sorted by id)"
    ]


def test_unknown_schema_fails(tmp_path: Path) -> None:
    paths = workspace(tmp_path, [])
    record = json.loads(paths.record.read_text(encoding="utf-8"))
    record["schema"] = "ibex.deprecations.v2"
    paths.record.write_text(json.dumps(record, indent=2) + "\n", encoding="utf-8")
    assert cli.check(paths) == [
        (f"unknown-enum: record schema is 'ibex.deprecations.v2'; expected {cli.SCHEMA!r}")
    ]


def test_deeply_nested_record_fails_closed(tmp_path: Path) -> None:
    """A parse failure is a diagnostic, not an uncaught RecursionError."""
    paths = workspace(tmp_path, [])
    paths.record.write_text("[" * 100_000 + "]" * 100_000, encoding="utf-8")
    failures = cli.check(paths)
    assert len(failures) == 1, failures
    assert failures[0].startswith(f"invalid-record: {paths.record}: ")
    assert "nested too deeply" in failures[0]


def test_main_checks_a_record_in_a_temp_tree(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """The CLI takes every input as a path, so the positive case is reproducible."""
    paths = workspace(tmp_path, [current_entry(180)])
    args = argv(paths)
    assert cli.main(args) == 0
    assert f"deprecation record is valid: {paths.record}" in capsys.readouterr().out

    workspace(tmp_path, [current_entry(179)])
    assert cli.main(args) == 1
    assert "window-too-short" in capsys.readouterr().err


def test_empty_record_note_is_conditional(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """The note is true only of the empty record; printing it for entries misleads."""
    paths = workspace(tmp_path, [current_entry(180)])
    args = argv(paths)
    assert cli.main(args) == 0
    out = capsys.readouterr().out
    assert f"deprecation record is valid: {paths.record}" in out
    assert "empty entries array means nothing is deprecated" not in out

    workspace(tmp_path, [])
    assert cli.main(args) == 0
    assert "note: an empty entries array means nothing is deprecated" in capsys.readouterr().out
