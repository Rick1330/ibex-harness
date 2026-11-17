#!/usr/bin/env python3
"""Fail when the OSV waiver record has drifted or is about to expire.

`osv-scanner.toml` is the policy the scanner enforces; the "Active SCA waivers"
table in `engineering/DEPENDENCIES.md` is what a human reads. They are edited by
hand and nothing compared them, so a waiver could be added (picomatch,
GHSA-fc5q-39xc-vjpf) and never reach the table, leaving an advisory suppressed
in CI with no recorded disposition.

Two properties are checked, both offline and stdlib-only:

1. **Parity.** The set of `[[IgnoredVulns]]` ids and the set of GHSA ids in the
   table must be equal. A mismatch in either direction fails: an id only in the
   TOML is a suppression nobody recorded, and an id only in the table is a
   disposition that suppresses nothing (a stale row after the advisory was
   fixed). A table date that disagrees with its `ignoreUntil` fails too, because
   a reader who renews only one file would otherwise see a green check.

2. **Lead time.** Every waiver must expire no earlier than the lead window
   (`EXPIRY_LEAD_DAYS`). `ignoreUntil` is a hard cliff: on that date
   `osv-scanner` stops ignoring the advisory and `ci-gate-security` starts
   failing every mergeable PR at once -- including PRs with nothing to do with
   dependencies, because that gate is aggregate. Nineteen days of warning turns
   a repository-wide outage into a planned re-audit.

Why 21 days: it is three working weeks. It is long enough to fit a normal review
cycle (open a dependency PR, get it reviewed, let it merge) and to land the
decision to re-waive, and short enough that the alarm does not sit on the board
for a whole quarter while it is still true. A shorter window (a week) leaves no
room for a merge queue; a longer one is indistinguishable from "no alarm" at the
start of a quarter.

The check must never become the blocker it exists to prevent. Renewal is a
documented edit, not a code change: set `ignoreUntil` in `osv-scanner.toml` and
the matching `Expires` cell in the table to the new re-audit date, after the
re-audit the waiver's `reason` describes. Removing the waiver (because the
dependency was upgraded) is the other exit, and it needs both files edited too
-- which is what the parity check enforces.

Exit 1 on drift or a waiver inside the window, 2 when an input cannot be read,
parsed, or resolves outside this checkout, 0 otherwise.

Both path arguments are resolved and refused unless they land inside this
checkout, the same rule `validate-release-manifest.py` applies to its own
arguments: the policy and the table are repository files, so a path that escapes
the tree is a bad input, not a file to read.

Usage:
    python3 infra/scripts/check-osv-waivers.py
    python3 infra/scripts/check-osv-waivers.py --today 2026-11-20
    python3 infra/scripts/check-osv-waivers.py --config ./osv-scanner.toml \\
        --table ./engineering/DEPENDENCIES.md
"""

from __future__ import annotations

import argparse
import datetime
import pathlib
import re
import sys
import tomllib
from dataclasses import dataclass

REPO_ROOT = pathlib.Path(__file__).resolve().parents[2]
DEFAULT_CONFIG = REPO_ROOT / "osv-scanner.toml"
DEFAULT_TABLE = REPO_ROOT / "engineering/DEPENDENCIES.md"

# The section that records the waivers. Scoped on purpose: DEPENDENCIES.md names
# GHSA ids elsewhere (packages that are fixed, not waived), and reading those as
# waivers would fail the parity check on every run.
TABLE_HEADING = "### 9.0.1a Active SCA waivers"
EXPIRY_COLUMN = "Expires"

# Three working weeks; see the module docstring for the reasoning.
EXPIRY_LEAD_DAYS = 21

ADVISORY_RE = re.compile(r"GHSA-[0-9a-z]{4}-[0-9a-z]{4}-[0-9a-z]{4}", re.IGNORECASE)
DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")


class InputError(Exception):
    """An input file is missing or no longer parses as the shape expected."""


@dataclass(frozen=True)
class Waiver:
    """One `[[IgnoredVulns]]` entry: its advisory id and the date it stops applying."""

    advisory: str
    expires: datetime.date


@dataclass(frozen=True)
class TableRow:
    """One waiver row: every advisory it names, and the date it records."""

    advisories: tuple[str, ...]
    expires: datetime.date | None
    line_number: int


@dataclass(frozen=True)
class Report:
    """One check's outcome: the header a failure prints, its notes, its problems."""

    header: str
    notes: tuple[str, ...]
    problems: tuple[str, ...]


def _contained_path(raw: pathlib.Path, label: str) -> pathlib.Path:
    """Resolve a CLI path and refuse anything outside this checkout.

    The policy and the table are repository files, so the only legitimate inputs
    live there. Resolving first means a relative path, a symlink pointing out of
    the tree, and an absolute path outside it are all judged by where they land,
    not by how they are spelled.
    """
    resolved = raw.resolve()
    if not resolved.is_relative_to(REPO_ROOT):
        raise InputError(f"{label} {raw} must resolve inside {REPO_ROOT}")
    return resolved


def _read_toml_document(path: pathlib.Path) -> dict:
    """Read and parse one TOML document, reporting I/O and syntax as InputError."""
    try:
        raw = path.read_bytes()
    except OSError as error:
        raise InputError(f"cannot read {path}: {error}") from error
    try:
        return tomllib.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, tomllib.TOMLDecodeError) as error:
        raise InputError(f"cannot parse {path}: {error}") from error


def _ignored_vuln_entries(document: dict, path: pathlib.Path) -> list[object]:
    """Return the `IgnoredVulns` array, or an empty list when it is absent."""
    entries = document.get("IgnoredVulns")
    if entries is None:
        # Absent is legitimate (no waivers) and distinct from a document that
        # stopped parsing: an empty list is the honest reading of "no entries".
        return []
    if not isinstance(entries, list):
        raise InputError(f"{path}: IgnoredVulns must be an array of tables")
    return entries


def _waiver_from_entry(entry: object, index: int, path: pathlib.Path) -> Waiver:
    """Read one `[[IgnoredVulns]]` entry, refusing one the check cannot use."""
    if not isinstance(entry, dict):
        raise InputError(f"{path}: IgnoredVulns entry {index} is not a table")
    advisory = str(entry.get("id", "")).strip()
    expires = entry.get("ignoreUntil")
    if not advisory:
        raise InputError(f"{path}: IgnoredVulns entry {index} has no id")
    if not isinstance(expires, datetime.date):
        # A missing or unquoted date would make the entry permanent without
        # anyone deciding that, which is the opposite of the policy.
        raise InputError(f"{path}: waiver {advisory} has no date-valued ignoreUntil")
    return Waiver(advisory=advisory.upper(), expires=expires)


def load_toml_waivers(path: pathlib.Path) -> list[Waiver]:
    """Return every `[[IgnoredVulns]]` entry with a usable id and expiry."""
    document = _read_toml_document(path)
    entries = _ignored_vuln_entries(document, path)
    return [
        _waiver_from_entry(entry, index, path)
        for index, entry in enumerate(entries, start=1)
    ]


def _read_text_document(path: pathlib.Path) -> str:
    """Read one text file, reporting I/O and decoding failures as InputError."""
    try:
        return path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError) as error:
        raise InputError(f"cannot read {path}: {error}") from error


def _waiver_section_lines(text: str) -> list[tuple[int, str]]:
    """Return the numbered lines that fall inside the waiver-table section.

    Any heading ends the section: the table is the whole of it. A section that is
    not there yields nothing, which the caller turns into an InputError so a
    renamed heading cannot be read as "no waivers".
    """
    lines: list[tuple[int, str]] = []
    in_section = False
    for number, line in enumerate(text.splitlines(), start=1):
        stripped = line.strip()
        if stripped.startswith("#"):
            if in_section:
                break
            in_section = stripped.startswith(TABLE_HEADING)
            continue
        if in_section:
            lines.append((number, line))
    return lines


def _table_lines(path: pathlib.Path) -> list[tuple[int, str]]:
    """Return the section's numbered lines: (1-based line number, text)."""
    lines = _waiver_section_lines(_read_text_document(path))
    if not lines:
        raise InputError(
            f"{path}: no '{TABLE_HEADING}' section; the waiver table was renamed "
            "or removed, so this check cannot compare anything"
        )
    return lines


def _cells(line: str) -> list[str]:
    """Split one markdown table row into its cells, without the outer pipes."""
    return [part.strip() for part in line.strip().strip("|").split("|")]


def _is_separator(cells: list[str]) -> bool:
    """True for the `| --- | --- |` line under the header."""
    return all(cell and set(cell) <= {"-", ":"} for cell in cells)


def _parse_expiry(cell: str) -> datetime.date | None:
    """Read the `Expires` cell, or None when it is not an ISO date."""
    candidate = cell.strip().strip("`").strip()
    if not DATE_RE.match(candidate):
        return None
    try:
        return datetime.date.fromisoformat(candidate)
    except ValueError:
        return None


def _require_expiry_column(cells: list[str], number: int, path: pathlib.Path) -> None:
    """Refuse a header that no longer carries the `Expires` column."""
    if EXPIRY_COLUMN not in cells:
        raise InputError(
            f"{path}:{number}: waiver table has no {EXPIRY_COLUMN!r} column"
        )


def _row_from_cells(cells: list[str], number: int, path: pathlib.Path) -> TableRow:
    """Read one data row, refusing a row that names no advisory."""
    advisories = tuple(
        match.group(0).upper() for match in ADVISORY_RE.finditer(cells[0])
    )
    if not advisories:
        raise InputError(
            f"{path}:{number}: waiver row names no GHSA advisory: {cells[0]!r}"
        )
    return TableRow(
        advisories=advisories,
        expires=_parse_expiry(cells[-1]),
        line_number=number,
    )


def _table_rows(path: pathlib.Path) -> list[TableRow]:
    """Return the section's data rows, reading the header once."""
    rows: list[TableRow] = []
    saw_header = False
    for number, line in _table_lines(path):
        if not line.strip().startswith("|"):
            continue
        cells = _cells(line)
        if not saw_header:
            # The first row is the header; if the column moved, the positions
            # this parser relies on are gone and reading on would compare the
            # wrong cell.
            _require_expiry_column(cells, number, path)
            saw_header = True
            continue
        if _is_separator(cells):
            continue
        rows.append(_row_from_cells(cells, number, path))
    return rows


def parse_table(path: pathlib.Path) -> list[TableRow]:
    """Return the waiver rows: their advisory ids and recorded expiry."""
    rows = _table_rows(path)
    if not rows:
        raise InputError(f"{path}: the waiver table has no rows")
    return rows


def table_advisories(rows: list[TableRow]) -> dict[str, TableRow]:
    """Map every advisory named by the table to the row that names it."""
    found: dict[str, TableRow] = {}
    for row in rows:
        for advisory in row.advisories:
            found.setdefault(advisory, row)
    return found


def check_parity(waivers: list[Waiver], rows: list[TableRow]) -> tuple[list[str], list[str]]:
    """Return (notes, problems) for the id sets in both directions."""
    notes: list[str] = []
    problems: list[str] = []

    toml_ids = {waiver.advisory for waiver in waivers}
    recorded = table_advisories(rows)

    for advisory in sorted(toml_ids - set(recorded)):
        problems.append(
            f"{advisory} is ignored in osv-scanner.toml but has no row in the "
            f"{TABLE_HEADING} table"
        )
    for advisory in sorted(set(recorded) - toml_ids):
        problems.append(
            f"{advisory} is recorded in the waiver table "
            f"(engineering/DEPENDENCIES.md:{recorded[advisory].line_number}) but "
            "no longer ignored in osv-scanner.toml"
        )

    if not problems:
        notes.append(f"{len(toml_ids)} waived advisor{'' if len(toml_ids) == 1 else 'ies'} match the recorded table")
    return notes, problems


def check_expiry(
    waivers: list[Waiver], today: datetime.date, lead_days: int = EXPIRY_LEAD_DAYS
) -> tuple[list[str], list[str]]:
    """Return (notes, problems) for waivers inside the lead window."""
    notes: list[str] = []
    problems: list[str] = []
    for waiver in sorted(waivers, key=lambda item: item.expires):
        remaining = (waiver.expires - today).days
        if remaining < 0:
            problems.append(
                f"{waiver.advisory} expired on {waiver.expires.isoformat()} "
                f"({-remaining} days ago); the scanner ignores it no longer"
            )
        elif remaining <= lead_days:
            problems.append(
                f"{waiver.advisory} expires on {waiver.expires.isoformat()} "
                f"({remaining} days from {today.isoformat()})"
            )
        else:
            notes.append(
                f"{waiver.advisory} expires {waiver.expires.isoformat()} ({remaining} days)"
            )
    return notes, problems


def check_recorded_dates(
    waivers: list[Waiver], rows: list[TableRow]
) -> tuple[list[str], list[str]]:
    """Return (notes, problems) for table dates that disagree with the TOML.

    The TOML is what the scanner enforces and the table is what a human reads, so
    a disagreement is exactly the drift the parity check exists for: someone who
    renews only one file would otherwise see a green check and a stale record.
    """
    notes: list[str] = []
    problems: list[str] = []
    recorded = table_advisories(rows)
    for waiver in waivers:
        row = recorded.get(waiver.advisory)
        if row is None:
            continue
        if row.expires is None:
            problems.append(
                f"{waiver.advisory}: the table row at "
                f"engineering/DEPENDENCIES.md:{row.line_number} has no ISO date in "
                f"{EXPIRY_COLUMN!r}"
            )
        elif row.expires != waiver.expires:
            problems.append(
                f"{waiver.advisory}: the table records {row.expires.isoformat()} "
                f"but osv-scanner.toml carries ignoreUntil = {waiver.expires.isoformat()}"
            )
    if not problems:
        notes.append("every recorded expiry matches its ignoreUntil")
    return notes, problems


def _renewal_hint() -> str:
    return (
        "\nA waiver is renewed by editing, not by code:\n"
        "  1. re-audit the advisory the way its `reason` describes;\n"
        "  2. set `ignoreUntil` to the new re-audit date in osv-scanner.toml;\n"
        "  3. set the same date in that advisory's `Expires` cell in\n"
        f"     engineering/DEPENDENCIES.md ({TABLE_HEADING});\n"
        "  4. or remove both entries, which is the correct exit when the\n"
        "     dependency has been upgraded past the advisory.\n"
    )


def _report(report: Report) -> None:
    """Print a check's problems to stderr, or its notes to stdout when it passed."""
    if report.problems:
        print(f"check-osv-waivers: {report.header}", file=sys.stderr)
        for problem in report.problems:
            print(f"  {problem}", file=sys.stderr)
        return
    for note in report.notes:
        print(f"check-osv-waivers: {note}")


def check_all(
    waivers: list[Waiver], rows: list[TableRow], today: datetime.date, lead_days: int
) -> list[Report]:
    """Run every check and return its outcome, so main only reports and decides."""
    parity_notes, parity_problems = check_parity(waivers, rows)
    date_notes, date_problems = check_recorded_dates(waivers, rows)
    expiry_notes, expiry_problems = check_expiry(waivers, today, lead_days)
    return [
        Report(
            header="the ignored advisories and the recorded waivers disagree:",
            notes=tuple(parity_notes),
            problems=tuple(parity_problems),
        ),
        Report(
            header="the waiver record carries two different expiry dates:",
            notes=tuple(date_notes),
            problems=tuple(date_problems),
        ),
        Report(
            header=f"a waiver expires within {lead_days} days ({today.isoformat()}):",
            notes=tuple(expiry_notes),
            problems=tuple(expiry_problems),
        ),
    ]


def _parse_args(argv: list[str] | None) -> argparse.Namespace:
    """Parse the command line: two contained paths, a date, and the lead window."""
    parser = argparse.ArgumentParser(
        description="Fail when the OSV waiver record drifts or nears expiry.",
    )
    parser.add_argument("--config", type=pathlib.Path, default=DEFAULT_CONFIG)
    parser.add_argument("--table", type=pathlib.Path, default=DEFAULT_TABLE)
    parser.add_argument(
        "--today",
        type=datetime.date.fromisoformat,
        # UTC, not local time: this is a date-based gate, and a local "today"
        # would let the alarm fire a day early or a day late depending on the
        # runner's timezone. CI and an operator's machine must agree.
        default=datetime.datetime.now(datetime.UTC).date(),
        help="reference date for the expiry window (default: today, UTC)",
    )
    parser.add_argument(
        "--lead-days",
        type=int,
        default=EXPIRY_LEAD_DAYS,
        help=f"warn this many days before expiry (default: {EXPIRY_LEAD_DAYS})",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv)

    try:
        waivers = load_toml_waivers(_contained_path(args.config, "--config"))
        rows = parse_table(_contained_path(args.table, "--table"))
    except InputError as error:
        print(f"check-osv-waivers: {error}", file=sys.stderr)
        return 2

    reports = check_all(waivers, rows, args.today, args.lead_days)
    for report in reports:
        _report(report)

    if any(report.problems for report in reports):
        print(_renewal_hint(), file=sys.stderr)
        return 1
    print(
        "check-osv-waivers: the waiver record matches and every expiry is "
        "beyond the window"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
