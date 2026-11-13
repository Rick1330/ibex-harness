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

# A quoted or unquoted SQL identifier. A quoted identifier may contain a dot, so
# `"my.schema"."table"` stays two identifier tokens rather than three. A doubled
# quote inside one (`"we""ird"`) is that quote once, so the pattern reads the
# whole identifier instead of stopping at the first closing quote and keying the
# table as something else.
_IDENTIFIER = r'(?:"(?:[^"]|"")*"|`[^`]*`|\[[^\]]*\]|[A-Za-z_][\w$]*)'

# `CREATE TABLE [IF NOT EXISTS] <schema>.<name>` and the unqualified form.
# UNLOGGED/TEMP are accepted so a future migration is parsed, not silently
# skipped: an unparsed CREATE TABLE would be an invisible gap in the gate.
CREATE_TABLE_RE = re.compile(
    r"\bCREATE\s+(?:UNLOGGED\s+|GLOBAL\s+|LOCAL\s+|TEMPORARY\s+|TEMP\s+|FOREIGN\s+)?TABLE\s+"
    r"(?:IF\s+NOT\s+EXISTS\s+)?"
    rf"(?P<first>{_IDENTIFIER})"
    rf"(?:\s*\.\s*(?P<second>{_IDENTIFIER}))?",
    re.IGNORECASE,
)

# The qualifiers PostgreSQL accepts between CREATE and TABLE. The keyword scan
# matches any single word there and validates it against this set, so the pattern
# stays simple and the accepted set stays readable in one place.
CREATE_TABLE_QUALIFIERS = frozenset(
    {"UNLOGGED", "GLOBAL", "LOCAL", "TEMPORARY", "TEMP", "FOREIGN"}
)

# Every `CREATE TABLE` keyword sequence, used to prove each one parses. A
# CREATE TABLE the identifier pattern cannot follow is a structural error, not a
# table the gate may skip. The word before TABLE is matched loosely and filtered
# through CREATE_TABLE_QUALIFIERS; the lookahead keeps a table literally named
# `table` (`CREATE TABLE table`) parsing as the unqualified form.
CREATE_TABLE_KEYWORD_RE = re.compile(
    r"\bCREATE\s+(?:(?P<qualifier>(?!TABLE\b)\w+)\s+)?TABLE\b", re.IGNORECASE
)

# A fenced-code opener's marker: an optional indent, then three or more
# backticks or three or more tildes. The info string is the rest of the line and
# is sliced off after the match, so no quantifier can overlap the marker run and
# the match stays linear.
FENCE_MARKER_RE = re.compile(r"^\s*(?P<marker>`{3,}|~{3,})")

# A per-table heading, e.g. ##### `ibex_core.memory_feedback` (migration `000023`).
# This is the compact entry form used by the "applied tables" section; a table is
# documented by exactly one of the two forms (DDL in a sql fence, or a heading).
HEADING_TABLE_RE = re.compile(
    r"^\s*#{3,6}\s+"
    r"(?:`(?P<quoted>[A-Za-z_][\w$]*(?:\.[A-Za-z_][\w$]*)?)`"
    r"|(?P<bare>[A-Za-z_][\w$]*\.[A-Za-z_][\w$]*))"
)

# `$tag$` or `$$`, the PostgreSQL dollar-quote delimiter. The tag follows the
# unquoted-identifier rules except that it may not contain `$`: a letter
# (Unicode letters included) or an underscore, then letters, digits, and
# underscores. `[^\W\d]` is "a word character that is not a digit", so `$café$`
# is a tag, `$1$` is not (PostgreSQL reads that as a parameter), and a tag stops
# at the first `$` it meets.
DOLLAR_TAG_RE = re.compile(r"\$(?:[^\W\d]\w*)?\$")

# The last word of the SQL emitted so far, for the checks that need to know
# which statement position the next token sits in. `\w` is Unicode-aware, so
# `caféDO` reads as one word rather than as the `DO` keyword.
_LAST_WORD_RE = re.compile(r"(?<![\w$])(?P<word>[A-Za-z_]\w*)\Z")

_QUOTE_PAIRS = (('"', '"'), ("`", "`"), ("[", "]"))


class DocError(Exception):
    """The doc is structurally unreadable; the gate must fail loudly."""


def _blank(text: str) -> str:
    """Spaces with newlines preserved, so line numbers stay meaningful."""
    return "".join("\n" if char == "\n" else " " for char in text)


def strip_sql_comments_and_literals(sql: str, dynamic: bool = False) -> str:
    """Blank comments and string literals, keeping newlines and byte offsets.

    Quoted identifiers are copied verbatim because a CREATE TABLE may quote its
    schema and table names; their contents are skipped so an apostrophe inside
    one does not open a string. String literals (single-quoted and
    dollar-quoted) are blanked so a `CREATE TABLE` inside one is not DDL.

    `dynamic` marks a `DO $tag$ … $tag$` body, the one place PostgreSQL runs
    text this file would otherwise call data: the body is scanned as SQL, and so
    is the literal of an `EXECUTE '…'` inside it.
    """
    out: list[str] = []
    index = 0
    while index < len(sql):
        end = _blank_token(sql, index, out, dynamic)
        if end is None:
            out.append(sql[index])
            index += 1
        else:
            index = end
    return "".join(out)


def _blank_token(sql: str, index: int, out: list[str], dynamic: bool) -> int | None:
    """Blank the comment or literal starting at index, or None for ordinary SQL.

    Returns the index just past the token. Every branch keeps the byte count, so
    the caller can treat the result as an offset-preserving replacement.
    """
    if sql.startswith("--", index):
        return _blank_line_comment(sql, index, out)
    if sql.startswith("/*", index):
        return _blank_block_comment(sql, index, out)
    if sql[index] == "'":
        return _blank_quoted(
            sql, index, out, dynamic and _ends_with_keyword(out, "EXECUTE")
        )
    if sql[index] == '"':
        return _keep_quoted(sql, index, out, '"')
    tag = _dollar_tag(sql, index) if sql[index] == "$" else None
    if tag:
        return _blank_dollar_quoted(sql, index, out, tag)
    return None


def _blank_line_comment(sql: str, index: int, out: list[str]) -> int:
    end = sql.find("\n", index)
    if end == -1:
        end = len(sql)
    out.append(_blank(sql[index:end]))
    return end


def _blank_block_comment(sql: str, index: int, out: list[str]) -> int:
    """Blank `/* … */`, tracking depth: PostgreSQL nests block comments."""
    depth = 0
    while index < len(sql):
        closed, depth, index = _consume_block_token(sql, index, out, depth)
        if closed:
            return index
    return index


def _consume_block_token(
    sql: str, index: int, out: list[str], depth: int
) -> tuple[bool, int, int]:
    """Consume one token inside a block comment.

    Returns (closed, depth, index): `closed` is True when the token was the `*/`
    that ended the outermost comment, in which case `index` is already past it.
    """
    if sql.startswith("/*", index):
        out.append("  ")
        return False, depth + 1, index + 2
    if sql.startswith("*/", index):
        out.append("  ")
        return depth == 1, depth - 1, index + 2
    out.append(_blank(sql[index]))
    return False, depth, index + 1


def _blank_quoted(sql: str, index: int, out: list[str], scan: bool) -> int:
    """Blank a single-quoted string, honouring doubled quotes.

    A backslash escapes the next character only when the string is an `E'…'`
    escape string. With `standard_conforming_strings` on — the default since
    PostgreSQL 9.1 — a backslash in an ordinary `'…'` is a literal character, so
    `'a\'` closes at the second quote and whatever follows is SQL again.

    `scan` marks the literal of an `EXECUTE '…'` inside a `DO` body: PostgreSQL
    runs that string, so its content is scanned as SQL instead of blanked.
    """
    escapes = _backslash_escapes(sql, index)
    out.append("'")
    start = index + 1
    index = start
    while index < len(sql):
        if sql.startswith("''", index):
            index += 2
        elif sql[index] == "'":
            _write_literal(sql[start:index], out, scan)
            out.append("'")
            return index + 1
        elif escapes and sql[index] == "\\":
            index += 2
        else:
            index += 1
    _write_literal(sql[start:], out, scan)
    return index


def _write_literal(content: str, out: list[str], scan: bool) -> None:
    """Write a literal's content: blanked as data, or scanned as SQL, same length."""
    out.append(
        strip_sql_comments_and_literals(content, dynamic=True)
        if scan
        else _blank(content)
    )


def _backslash_escapes(sql: str, index: int) -> bool:
    """True when the quote at index opens an `E'…'` (or `e'…'`) escape string.

    The prefix must start a token, so `xE'…'` is the identifier `xe` followed by
    an ordinary string, and `E` at the start of the file is a prefix.
    """
    if index == 0 or sql[index - 1] not in "eE":
        return False
    return index == 1 or not _is_identifier_char(sql[index - 2])


def _is_identifier_char(char: str) -> bool:
    """True for a character PostgreSQL accepts inside an unquoted identifier."""
    return char.isalnum() or char in "_$"


def _keep_quoted(sql: str, index: int, out: list[str], quote: str) -> int:
    """Copy a quoted identifier verbatim, skipping doubled-quote escapes."""
    out.append(quote)
    index += 1
    while index < len(sql):
        if sql.startswith(quote * 2, index):
            out.append(quote * 2)
            index += 2
        elif sql[index] == quote:
            out.append(quote)
            return index + 1
        else:
            out.append(sql[index])
            index += 1
    return index


def _dollar_tag(sql: str, index: int) -> str | None:
    match = DOLLAR_TAG_RE.match(sql, index)
    return match.group(0) if match else None


def _blank_dollar_quoted(sql: str, index: int, out: list[str], tag: str) -> int:
    """Blank a `$tag$ … $tag$` literal; dollar-quoted text has no escapes.

    The delimiters are blanked too: a tag could spell a keyword, and neither the
    body nor the tag is executable SQL. A `DO` block is the exception: its body is
    plpgsql that runs, so a `CREATE TABLE` inside it creates a table and must
    reach the gate.
    """
    executable = _ends_with_keyword(out, "DO")
    blank_tag = _blank(tag)
    out.append(blank_tag)
    start = index + len(tag)
    end = sql.find(tag, start)
    if end == -1:
        out.append(_dollar_body(sql[start:], executable))
        return len(sql)
    out.append(_dollar_body(sql[start:end], executable))
    out.append(blank_tag)
    return end + len(tag)


def _dollar_body(body: str, executable: bool) -> str:
    """A dollar-quoted body as it stands in the output, keeping its byte count."""
    if executable:
        return strip_sql_comments_and_literals(body, dynamic=True)
    return _blank(body)


def _ends_with_keyword(prefix: list[str], keyword: str) -> bool:
    """True when the SQL emitted so far ends with `keyword` as a whole word.

    Comments and literals are already blanked in `prefix`, so a keyword in prose
    cannot match. `DO` is the only statement with an executable dollar-quoted
    body; `EXECUTE` is the only keyword whose string literal runs. `format(…)`
    and concatenation are not literals of either, so dynamic SQL built that way
    stays data, exactly as a string literal is data everywhere else in this file.
    """
    match = _LAST_WORD_RE.search("".join(prefix).rstrip())
    return match is not None and match.group("word").upper() == keyword


def normalise(identifier: str) -> str:
    """Canonical identity of an identifier token.

    PostgreSQL folds an unquoted identifier to lower case and keeps a quoted one
    exactly as written, so `ibex_core.users` and `ibex_core."Users"` are two
    different tables and must stay two different keys.
    """
    ident = identifier.strip()
    if _quote_pair(ident) is None:
        return ident.lower()
    return _unquote(ident)


def _quote_pair(ident: str) -> tuple[str, str] | None:
    """The quote pair surrounding ident, or None when it is unquoted."""
    for left, right in _QUOTE_PAIRS:
        if _wrapped_in(ident, left, right):
            return left, right
    return None


def _unquote(ident: str) -> str:
    """The identifier's content: one quote pair removed and its escapes resolved.

    The original case is kept, because that is the identity a quoted identifier
    has. A doubled closing quote inside one spells that quote once.
    """
    pair = _quote_pair(ident)
    if pair is None:
        return ident
    left, right = pair
    return ident[1:-1].replace(left + right, right)


def _wrapped_in(ident: str, left: str, right: str) -> bool:
    """True when ident is at least two characters and starts and ends with the pair."""
    if len(ident) < 2:
        return False
    return ident[0] == left and ident[-1] == right


def table_keys(sql: str) -> list[str]:
    """Return canonical `schema.name` (or bare `name`) keys, in file order."""
    cleaned = strip_sql_comments_and_literals(sql)
    return [_table_key(match) for match in _create_table_matches(cleaned)]


def _create_table_keywords(cleaned: str) -> list[re.Match[str]]:
    """Every `CREATE [<qualifier>] TABLE` whose qualifier PostgreSQL accepts."""
    return [
        match
        for match in CREATE_TABLE_KEYWORD_RE.finditer(cleaned)
        if _accepted_qualifier(match.group("qualifier"))
    ]


def _accepted_qualifier(word: str | None) -> bool:
    """True for the unqualified form and for a qualifier PostgreSQL accepts."""
    return word is None or word.upper() in CREATE_TABLE_QUALIFIERS


def _create_table_matches(cleaned: str) -> list[re.Match[str]]:
    """Match every CREATE TABLE, failing loudly when one cannot be parsed."""
    matches: list[re.Match[str]] = []
    for keyword in _create_table_keywords(cleaned):
        match = CREATE_TABLE_RE.match(cleaned, keyword.start())
        if match is None:
            line = cleaned.count("\n", 0, keyword.start()) + 1
            raise DocError(
                f"cannot parse CREATE TABLE at line {line}: {_line_at(cleaned, keyword.start())!r}"
            )
        matches.append(match)
    return matches


def _line_at(text: str, index: int) -> str:
    start = text.rfind("\n", 0, index) + 1
    end = text.find("\n", index)
    return text[start : len(text) if end == -1 else end].strip()


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
        raise DocError(
            f"doc headings are out of order: {PG_HEADING!r} must precede {CH_HEADING!r}"
        )
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
        opener = _fence_opener(lines[index])
        if opener is None:
            index += 1
            continue
        marker, info = opener
        body: list[str] = []
        body_start = index + 1
        index += 1
        while index < len(lines) and not _is_fence_closer(lines[index], marker):
            body.append(lines[index])
            index += 1
        if info.lower() in ("", "sql", "postgres", "postgresql"):
            blocks.append((body_start, "\n".join(body)))
        index += 1
    return blocks


def _fence_opener(line: str) -> tuple[str, str] | None:
    """The (marker, info string) of a fence opener, or None for any other line.

    A backtick fence's info string may not contain a backtick, so a line of
    backticks inside a backtick fence is body text rather than a new opener.
    `line` is a single line: every caller passes an element of `splitlines()`.
    """
    match = FENCE_MARKER_RE.match(line)
    if match is None:
        return None
    marker = match.group("marker")
    info = line[match.end() :].strip()
    if marker[0] == "`" and "`" in info:
        return None
    return marker, info


def _is_fence_closer(line: str, marker: str) -> bool:
    """True when `line` closes a fence opened with `marker`.

    A closer must use the opener's marker character, be at least as long as the
    opener, and carry nothing but whitespace after it. A shorter run or a
    different marker is body text.
    """
    stripped = line.strip()
    if len(stripped) < len(marker):
        return False
    return stripped == marker[0] * len(stripped)


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


def _fenced_tables(
    region: list[str], heading_index: int
) -> tuple[dict[str, int], set[str]]:
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
    cleaned = strip_sql_comments_and_literals(block)
    return [
        (_table_key(match), cleaned.count("\n", 0, match.start()))
        for match in _create_table_matches(cleaned)
    ]


def _heading_tables(region: list[str], heading_index: int) -> dict[str, int]:
    """Tables documented by a per-table heading, keyed the same way as the fences.

    Headings inside a fenced code block are examples, not documentation, so the
    scan tracks fence state and ignores everything between an opener and its
    matching closer.
    """
    documented: dict[str, int] = {}
    marker: str | None = None
    for offset, line in enumerate(region):
        if marker is not None:
            if _is_fence_closer(line, marker):
                marker = None
            continue
        opener = _fence_opener(line)
        if opener is not None:
            marker = opener[0]
            continue
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


def _undocumented(
    migrations: dict[str, list[str]], documented: dict[str, int]
) -> list[str]:
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
        key
        for key in documented
        if key not in planning and not covered(key, migration_keys)
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
        print(
            f"FAIL: {doc_path} is out of sync with {MIGRATIONS_GLOB}", file=sys.stderr
        )
        for line in problems:
            print(line, file=sys.stderr)
        return 1
    print(summary)
    return 0


if __name__ == "__main__":
    sys.exit(main())
