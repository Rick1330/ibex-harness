#!/usr/bin/env python3
"""Gate: engineering/DATABASE_SCHEMA.md must not drift from the Postgres migrations.

P2-11. The doc is hand-written and covered fewer tables than the migrations
define. This check compares the two directions and fails on either:

  * a table a migration creates that the doc never names, and
  * a table the doc names that no migration creates.

Only the PostgreSQL region of the doc is checked (the `### PostgreSQL Schema`
heading up to `### ClickHouse Schema`). ClickHouse and Redis sketches are out of
scope here: the ClickHouse migration set has its own gate in
`infra/migrations/clickhouse/destructive_ddl_unit_test.go`, and the doc's
ClickHouse section is explicitly labelled as unapplied sketches.

Planning-only tables are declared in the doc itself, immediately above the
statement, with a comment containing the marker `schema-doc: not-migrated` plus
the reason. The doc therefore states which tables are sketches instead of this
script carrying a private allowlist. A table inside a planning-only block is
excluded from the "no migration creates it" direction.

Stdlib only, no database, no network: it reads files.

Usage:
    python3 infra/scripts/check-schema-doc.py
    python3 infra/scripts/check-schema-doc.py --doc /tmp/copy.md
    python3 infra/scripts/check-schema-doc.py --repo-root /path/to/repo
"""

from __future__ import annotations

import argparse
import pathlib
import re
import sys

MIGRATIONS_GLOB = "infra/migrations/postgres/*.up.sql"
DOC_PATH = "engineering/DATABASE_SCHEMA.md"

PG_HEADING = "### PostgreSQL Schema"
CH_HEADING = "### ClickHouse Schema"

PLANNING_MARKER = "schema-doc: not-migrated"

# `CREATE TABLE [IF NOT EXISTS] <schema>.<name>` and the unqualified form.
# UNLOGGED/TEMP are accepted so a future migration is parsed, not silently
# skipped: an unparsed CREATE TABLE would be an invisible gap in the gate.
CREATE_TABLE_RE = re.compile(
    r"\bCREATE\s+(?:UNLOGGED\s+|GLOBAL\s+|LOCAL\s+|TEMPORARY\s+|TEMP\s+)?TABLE\s+"
    r"(?:IF\s+NOT\s+EXISTS\s+)?"
    r"(?P<first>[A-Za-z_][\w$]*)"
    r"(?:\s*\.\s*(?P<second>[A-Za-z_][\w$]*))?",
    re.IGNORECASE,
)

FENCE_RE = re.compile(r"^\s*```(?P<info>[\w+-]*)\s*$")

# A per-table heading, e.g. ##### `ibex_core.memory_feedback` (migration `000023`).
# This is the compact entry form used by the "applied tables" section; a table is
# documented by exactly one of the two forms (DDL in a sql fence, or a heading).
HEADING_TABLE_RE = re.compile(
    r"^\s*#{3,6}\s+"
    r"(?:`(?P<quoted>[A-Za-z_][\w$]*(?:\.[A-Za-z_][\w$]*)?)`"
    r"|(?P<bare>[A-Za-z_][\w$]*\.[A-Za-z_][\w$]*))"
)

LINE_COMMENT_RE = re.compile(r"--[^\n]*")
BLOCK_COMMENT_RE = re.compile(r"/\*.*?\*/", re.DOTALL)


class DocError(Exception):
    """The doc is structurally unreadable; the gate must fail loudly."""


def strip_sql_comments(text: str) -> str:
    """Blank SQL comments, keeping newlines so line numbers stay meaningful."""
    text = BLOCK_COMMENT_RE.sub(lambda m: re.sub(r"[^\n]", " ", m.group(0)), text)
    return LINE_COMMENT_RE.sub(lambda m: " " * len(m.group(0)), text)


def normalise(identifier: str) -> str:
    return identifier.strip().strip('"`[]').lower()


def table_keys(sql: str) -> list[str]:
    """Return canonical `schema.name` (or bare `name`) keys, in file order."""
    return [_table_key(match) for match in CREATE_TABLE_RE.finditer(strip_sql_comments(sql))]


def _table_key(match: re.Match[str]) -> str:
    """`schema.name` when the CREATE TABLE qualifies the table, else the bare name."""
    first = normalise(match.group("first"))
    second = match.group("second")
    return f"{first}.{normalise(second)}" if second else first


def migration_tables(migrations_dir: pathlib.Path) -> dict[str, list[str]]:
    """Map canonical table key -> sorted list of migration files creating it."""
    if not migrations_dir.is_dir():
        raise DocError(f"migrations directory not found: {migrations_dir}")
    files = sorted(migrations_dir.glob("*.up.sql"))
    if not files:
        raise DocError(f"no *.up.sql migrations found in {migrations_dir}")
    found: dict[str, list[str]] = {}
    for path in files:
        for key in table_keys(path.read_text(encoding="utf-8")):
            found.setdefault(key, []).append(path.name)
    return found


def postgres_region(doc_text: str) -> tuple[int, list[str]]:
    """Return (line index of the PostgreSQL heading, its lines up to ClickHouse)."""
    lines = doc_text.splitlines()
    start = _heading_index(lines, PG_HEADING)
    end = _heading_index(lines, CH_HEADING)
    if end <= start:
        raise DocError(f"doc headings are out of order: {PG_HEADING!r} must precede {CH_HEADING!r}")
    return start, lines[start:end]


def _heading_index(lines: list[str], heading: str) -> int:
    for index, line in enumerate(lines):
        if line.strip() == heading:
            return index
    raise DocError(f"doc is missing the {heading!r} heading")


def fenced_sql_blocks(lines: list[str]) -> list[tuple[int, str]]:
    """Return (0-based line offset within `lines`, block text) for SQL fences."""
    blocks: list[tuple[int, str]] = []
    index = 0
    while index < len(lines):
        opening = FENCE_RE.match(lines[index])
        if not opening:
            index += 1
            continue
        info = opening.group("info").lower()
        body: list[str] = []
        body_start = index + 1
        index += 1
        while index < len(lines) and not FENCE_RE.match(lines[index]):
            body.append(lines[index])
            index += 1
        if info in ("", "sql", "postgres", "postgresql"):
            blocks.append((body_start, "\n".join(body)))
        index += 1
    return blocks


def is_planning_only(block_lines: list[str], statement_offset: int) -> bool:
    """True when the comment block directly above a statement carries the marker.

    The scan stops at the first non-comment line, so a marker cannot leak onto a
    later, applied statement in the same fence.
    """
    index = statement_offset - 1
    while index >= 0:
        stripped = block_lines[index].strip()
        if not stripped:
            return False
        if not stripped.startswith("--"):
            return False
        if PLANNING_MARKER in stripped:
            return True
        index -= 1
    return False


def doc_tables(doc_text: str) -> tuple[dict[str, int], set[str]]:
    """Return (documented applied tables -> line number, planning-only tables).

    A table is documented either as a `CREATE TABLE` inside a sql fence or as a
    per-table heading. Both forms are structural, so a passing mention of a name
    in prose does not satisfy the gate.
    """
    heading_index, region = postgres_region(doc_text)
    documented, planning = _fenced_tables(region, heading_index)
    for key, line in _heading_tables(region, heading_index).items():
        documented.setdefault(key, line)
    return documented, planning


def _fenced_tables(region: list[str], heading_index: int) -> tuple[dict[str, int], set[str]]:
    """Tables the sql fences document, split into applied DDL and planning-only sketches."""
    documented: dict[str, int] = {}
    planning: set[str] = set()
    for body_start, block in fenced_sql_blocks(region):
        _collect_fence(block, heading_index + body_start, documented, planning)
    return documented, planning


def _collect_fence(
    block: str,
    first_line: int,
    documented: dict[str, int],
    planning: set[str],
) -> None:
    """Record one fence's tables; a statement under the planning marker is a sketch."""
    block_lines = block.splitlines()
    for key, offset in _block_tables(block):
        if is_planning_only(block_lines, offset):
            planning.add(key)
        else:
            documented.setdefault(key, first_line + offset + 1)


def _block_tables(block: str) -> list[tuple[str, int]]:
    """(table key, line offset within the block) for each CREATE TABLE in a fence."""
    return [
        (_table_key(match), block.count("\n", 0, match.start()))
        for match in CREATE_TABLE_RE.finditer(strip_sql_comments(block))
    ]


def _heading_tables(region: list[str], heading_index: int) -> dict[str, int]:
    """Tables documented by a per-table heading, keyed the same way as the fences."""
    documented: dict[str, int] = {}
    for offset, line in enumerate(region):
        key = _heading_key(line)
        if key is not None:
            documented.setdefault(key, heading_index + offset + 1)
    return documented


def _heading_key(line: str) -> str | None:
    """The table a per-table heading names, or None for any other line."""
    heading = HEADING_TABLE_RE.match(line)
    if heading is None:
        return None
    return normalise(heading.group("quoted") or heading.group("bare"))


def covered(key: str, candidates: set[str]) -> bool:
    """A bare key matches any schema; a qualified key must match exactly."""
    if key in candidates:
        return True
    if "." in key:
        return False
    return any(candidate.split(".", 1)[-1] == key for candidate in candidates)


def check(repo_root: pathlib.Path, doc_path: pathlib.Path) -> tuple[list[str], str]:
    """Return (problems, summary). Empty problems means the gate passes."""
    migrations = migration_tables(repo_root / "infra/migrations/postgres")
    documented, planning = doc_tables(doc_path.read_text(encoding="utf-8"))

    problems = _drift_problems(migrations, documented, planning)
    if problems:
        return problems, ""

    applied = len(set(documented) - planning)
    summary = (
        f"OK: {len(migrations)} migration tables documented in {doc_path.name} "
        f"({applied} applied, {len(planning)} planning-only sketches); "
        f"{file_count(repo_root)} up migrations scanned"
    )
    return [], summary


def _drift_problems(
    migrations: dict[str, list[str]],
    documented: dict[str, int],
    planning: set[str],
) -> list[str]:
    """Both directions of the comparison, each a header line plus one line per table."""
    missing = _undocumented(migrations, documented)
    unknown = _unmigrated(documented, migrations, planning)
    return [*_missing_lines(missing, migrations), *_unknown_lines(unknown, documented)]


def _undocumented(migrations: dict[str, list[str]], documented: dict[str, int]) -> list[str]:
    """Tables a migration creates that the doc never names."""
    documented_keys = set(documented)
    return sorted(key for key in migrations if not covered(key, documented_keys))


def _unmigrated(
    documented: dict[str, int],
    migrations: dict[str, list[str]],
    planning: set[str],
) -> list[str]:
    """Tables the doc names that no migration creates and no planning marker exempts."""
    migration_keys = set(migrations)
    return sorted(
        key for key in documented if key not in planning and not covered(key, migration_keys)
    )


def _missing_lines(missing: list[str], migrations: dict[str, list[str]]) -> list[str]:
    if not missing:
        return []
    return [
        f"created by a migration but not documented ({len(missing)}):",
        *(f"  - {key}  (from {', '.join(migrations[key])})" for key in missing),
    ]


def _unknown_lines(unknown: list[str], documented: dict[str, int]) -> list[str]:
    if not unknown:
        return []
    return [
        f"documented but no migration creates it ({len(unknown)}):",
        *(f"  - {key}  (doc line {documented[key]})" for key in unknown),
    ]


def file_count(repo_root: pathlib.Path) -> int:
    return len(list((repo_root / "infra/migrations/postgres").glob("*.up.sql")))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Fail when DATABASE_SCHEMA.md drifts from the Postgres migrations."
    )
    parser.add_argument(
        "--repo-root",
        type=pathlib.Path,
        default=pathlib.Path(__file__).resolve().parents[2],
        help="repository root (default: two levels above this script)",
    )
    parser.add_argument(
        "--doc",
        type=pathlib.Path,
        default=None,
        help=f"doc to check (default: <repo-root>/{DOC_PATH})",
    )
    args = parser.parse_args(argv)

    repo_root: pathlib.Path = args.repo_root
    doc_path: pathlib.Path = args.doc or repo_root / DOC_PATH

    try:
        problems, summary = check(repo_root, doc_path)
    except DocError as error:
        print(f"FAIL: {error}", file=sys.stderr)
        return 2
    except OSError as error:
        print(f"FAIL: cannot read input: {error}", file=sys.stderr)
        return 2

    if problems:
        print(f"FAIL: {doc_path} is out of sync with {MIGRATIONS_GLOB}", file=sys.stderr)
        for line in problems:
            print(line, file=sys.stderr)
        return 1
    print(summary)
    return 0


if __name__ == "__main__":
    sys.exit(main())
