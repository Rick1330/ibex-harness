#!/usr/bin/env python3
"""Fail when the four places that state a capability's status disagree.

GAP-001: nothing prevented the status vocabulary drifting. Four surfaces state
it, and each is edited on its own:

1. ``engineering/architecture-v2/00-status-and-evidence.md`` -- the engineering
   ledger's "Current baseline" table. Its status column names a ledger class
   (``shipped-local``, ``provisional``, ``design-intent``, ``deferred``).
2. ``site/app/data/ledger.ts`` -- ``statusMeta`` (label to ledger class) and the
   ``capabilityRows`` the site and the Console render.
3. ``site/content/docs/02.architecture/05.status-and-evidence.md`` -- the public
   "Status vocabulary" table and the "Current baseline" table.
4. The ``site/content/docs`` mirrors -- the vocabulary list in
   ``01.getting-started/02.concepts.md`` and the baseline table in
   ``01.getting-started/01.introduction.md``.

Three properties are checked, offline and stdlib-only:

1. **One vocabulary.** ``Status`` in ``ledger.ts`` is the declared label set.
   ``statusMeta``, the public vocabulary table, and the concepts list must name
   exactly that set, and the label-to-class map must agree between
   ``ledger.ts`` and the public table. A label renamed in one file, or a class
   moved under a different label, fails naming the label.
2. **One status per capability.** Every capability a surface lists must carry
   the same status everywhere it is listed. A disagreement fails naming the
   capability and each surface's value. The engineering ledger states a class
   where the site states a label, so its cell is read as the first backticked
   class token and translated through the vocabulary before the comparison.
3. **No unaccounted row.** Every row of every surface must belong to a declared
   capability, and a declared capability must still be found where it is
   declared. A capability added, renamed, or dropped in one surface fails here
   instead of passing unscanned, which is the drift this guard exists for. A row
   or a label the reader cannot parse, or a label listed twice, is an input error
   rather than an entry to skip: skipping it would leave it out of the comparison
   while it stayed visible to a reader. The same holds for every element of
   ``capabilityRows``: one that is not one single-quoted tuple on its own line --
   a spread, a second tuple on the line, a tuple broken across lines -- is
   rejected naming its line rather than dropped from the comparison.

What is *not* compared, and why:

- **The limitation columns.** "What must not be inferred" in the engineering
  ledger and "Must not be inferred" on the site are free prose, written
  separately for each audience and deliberately not identical: the site names
  what a reader must not conclude, the engineering ledger names the evidence
  that is missing. There is no shared key to compare, so a prose comparison
  would either be meaningless or force two audiences to share a sentence
  neither wants. The status columns are the mechanical contract.
- **Tables that use another vocabulary.** ``11.operations/08.console.md`` states
  Console surface availability (``Live D1``, ``Preview``, ADR-0089), not a
  capability status, and ``11.operations/06.billing-and-budgets.md`` states
  per-store notes in prose. Both would be false positives, so the surfaces are
  declared explicitly instead of discovered by "any table with a Status
  column".

Exit 1 on drift, 2 when a surface cannot be read or parsed, 0 otherwise.

Usage:
    python3 infra/scripts/check-status-vocabulary.py
    python3 infra/scripts/check-status-vocabulary.py --root .
"""

from __future__ import annotations

import argparse
import re
import sys
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]

ENGINEERING_LEDGER = "engineering/architecture-v2/00-status-and-evidence.md"
SITE_LEDGER = "site/app/data/ledger.ts"
DOCS_LEDGER = "site/content/docs/02.architecture/05.status-and-evidence.md"
DOCS_VOCABULARY = "site/content/docs/01.getting-started/02.concepts.md"
DOCS_MIRROR = "site/content/docs/01.getting-started/01.introduction.md"


class InputError(Exception):
    """A surface could not be read or parsed as the table it is expected to be."""


@dataclass(frozen=True)
class Surface:
    """A markdown baseline table: which file, and which two columns to read."""

    key: str
    path: str
    capability_column: str
    status_column: str
    states_ledger_class: bool = False


# The key each surface is known by. Each is written once here so both the tables
# below and the capability alias rows further down name a surface by constant: a
# misspelt surface is then a NameError at import, not a row the guard silently
# stops checking.
ENGINEERING, DOCS, LEDGER, MIRROR = "engineering", "docs", "ledger", "mirror"
SURFACE_KEYS = (ENGINEERING, DOCS, LEDGER, MIRROR)

SURFACES = (
    Surface(
        key=ENGINEERING,
        path=ENGINEERING_LEDGER,
        capability_column="Area",
        status_column="Current documented status",
        states_ledger_class=True,
    ),
    Surface(
        key=DOCS,
        path=DOCS_LEDGER,
        capability_column="Area",
        status_column="Status",
    ),
    Surface(
        key=MIRROR,
        path=DOCS_MIRROR,
        capability_column="Surface",
        status_column="Status",
    ),
)

# Which surfaces list which capability, under which name. The names are not
# identical across surfaces -- the engineering ledger writes "Auth/proxy
# foundations" where the site writes "Auth and proxy foundations" -- so the join
# is declared rather than inferred from a similarity rule that would silently
# pair the wrong rows.
#
# A capability is declared as one row per distinct wording: the wording, then
# every surface that uses it. A wording several surfaces share is written once,
# and a surface that words the capability differently keeps that difference
# visible as its own row rather than hiding it behind a shared label. A surface
# no row names does not list the capability.
#
# Adding a capability to any surface without adding it here fails check 3, which
# is the point: the guard is updated in the same change as the claim.
CAPABILITY_ALIASES: Mapping[str, tuple[tuple[str, ...], ...]] = {
    "auth-proxy": (
        ("Auth/proxy foundations", ENGINEERING),
        ("Auth and proxy foundations", DOCS, LEDGER, MIRROR),
    ),
    "management-api": (
        ("Management API", ENGINEERING, LEDGER, MIRROR),
        ("Management API · tenant routes", DOCS),
    ),
    "rate-limiting": (
        ("Rate limiting", ENGINEERING, DOCS, LEDGER),
    ),
    "provider-routing": (
        ("Provider routing, breakers, and fallback", ENGINEERING, DOCS),
        ("Provider routing and fallback", LEDGER),
    ),
    "proxy-slo": (
        ("Proxy overhead SLO and benchmark gate (GAP-004)", ENGINEERING),
        ("Proxy p99 and benchmark gate (GAP-004)", DOCS),
    ),
    "provider-packages": (
        ("Provider/tokenizer packages", ENGINEERING),
        ("Provider and tokenizer packages", DOCS),
    ),
    "memory": (
        ("Memory substrate", ENGINEERING, DOCS, LEDGER, MIRROR),
    ),
    "embedding-identity": (
        ("Embedding model identity (P1-30, P1-31)", ENGINEERING),
        ("Embedding model identity", DOCS, LEDGER),
    ),
    "context-assembly": (
        ("Context assembly", ENGINEERING, DOCS, LEDGER, MIRROR),
    ),
    "ranking-quality": (
        ("Ranking-quality benchmarks (v1 gold set, v2 mode comparison)", ENGINEERING),
        ("Ranking-quality benchmark (v1 gold set, v2 mode comparison)", DOCS),
        ("Ranking-quality benchmarks", LEDGER),
    ),
    "extraction": (
        ("Extraction workers", ENGINEERING, DOCS, LEDGER, MIRROR),
    ),
    "mcp-memory": (
        ("MCP memory tools", ENGINEERING, DOCS, LEDGER, MIRROR),
    ),
    "mcp-operator": (
        ("MCP operator gateway (GAP-009)", ENGINEERING),
        ("MCP operator gateway", DOCS, LEDGER, MIRROR),
    ),
    "budget": (
        ("Budget, usage, and cost", ENGINEERING, DOCS, LEDGER),
    ),
    "evidence-plane": (
        ("Evidence plane and relay", ENGINEERING, DOCS),
        ("Evidence plane", LEDGER),
    ),
    "console-live": (
        ("Operator Console core-tier live reads", ENGINEERING),
        ("Operator Console · live reads", DOCS, LEDGER),
        ("Operator Console", MIRROR),
    ),
    "console-preview": (
        ("Operator Console core-tier preview and platform tier", ENGINEERING),
        ("Operator Console · preview tiers", DOCS, LEDGER),
    ),
    "streaming": (
        ("Streaming hardening", ENGINEERING, DOCS, LEDGER),
    ),
    "v1-single-node": (
        ("v1-single-node deployment profile", ENGINEERING),
        ("`v1-single-node` deployment profile", DOCS),
        ("v1-single-node profile", LEDGER),
    ),
    "production-ops": (
        ("Production operations, HA, recovery, and release gates", ENGINEERING),
        ("Production operations and recovery", DOCS, LEDGER),
    ),
    "decisionservice": (
        ("DecisionService/GLiNER", ENGINEERING),
        ("DecisionService and GLiNER", DOCS, LEDGER),
        ("DecisionService, GLiNER", MIRROR),
    ),
    "graph": (
        ("Graph/A2A/marketplace/sandbox", ENGINEERING),
        ("Graph, A2A, marketplace, sandbox", DOCS, LEDGER, MIRROR),
    ),
}


def _alias_map(rows: Sequence[Sequence[str]]) -> dict[str, str | None]:
    """The surface-to-name map one capability's wording rows declare.

    Every surface is a key, in `SURFACE_KEYS` order -- the order the findings
    name surfaces in -- and a surface no row names maps to `None`.
    """
    named = {surface: row[0] for row in rows for surface in row[1:]}
    return {surface: named.get(surface) for surface in SURFACE_KEYS}


# The surface-to-name map the guard joins the surfaces on, built from the
# declaration above so each wording is written once.
CAPABILITIES: Mapping[str, Mapping[str, str | None]] = {
    capability: _alias_map(rows) for capability, rows in CAPABILITY_ALIASES.items()
}

TABLE_LINE = re.compile(r"^\s*\|.*\|\s*$")
SEPARATOR_CELL = re.compile(r"^:?-{3,}:?$")
CELL_SPLIT = re.compile(r"(?<!\\)\|")
STATUS_UNION = re.compile(r"export type Status = ([^\n]+)")
META_ENTRY = re.compile(r"^ {2}([A-Z][A-Z_]*): \{$", re.MULTILINE)
LEDGER_CLASS = re.compile(r"ledgerClass: '([^']+)'")
CAPABILITY_ROW = re.compile(r"^\s*\[\s*'([^']+)'\s*,\s*'([A-Z][A-Z_]*)'\s*,[^[]*\]\s*(?:,\s*)?$")
VOCABULARY_BULLET = re.compile(r"^[-*]\s+\*\*([A-Z][A-Z_]*)\*\*", re.MULTILINE)
CLASS_TOKEN = re.compile(r"`([a-z][a-z-]*)`")
DECORATION = re.compile(r"[`\s]")


def read(root: Path, relative: str) -> str:
    """The text of a repository file, or an InputError naming what is missing."""
    try:
        return (root / relative).read_text(encoding="utf-8")
    except OSError as error:
        raise InputError(f"{relative}: {error}") from error


def _cells(line: str) -> list[str]:
    return [cell.strip() for cell in CELL_SPLIT.split(line.strip().strip("|"))]


def _is_separator(line: str) -> bool:
    cells = _cells(line)
    return bool(cells) and all(SEPARATOR_CELL.match(cell) for cell in cells)


def _table_blocks(source: str) -> Iterable[list[tuple[int, str]]]:
    """Every run of consecutive pipe-table lines, each line with its 1-based number."""
    block: list[tuple[int, str]] = []
    for number, line in enumerate(source.splitlines(), start=1):
        if TABLE_LINE.match(line):
            block.append((number, line))
            continue
        if block:
            yield block
            block = []
    if block:
        yield block


def _is_table_block(block: Sequence[tuple[int, str]], columns: Sequence[str]) -> bool:
    """Whether a block's first two lines are the header of a table of `columns`."""
    if len(block) < 2 or not _is_separator(block[1][1]):
        return False
    return _cells(block[0][1])[: len(columns)] == list(columns)


def _parse_row(line: str, header_size: int, label: str) -> list[str]:
    """A table row as cells, or an InputError when it is not as wide as the header.

    A mis-split row would move a status into the capability column and compare
    prose, so a width mismatch is an input error rather than a row to keep.
    """
    cells = _cells(line)
    if len(cells) != header_size:
        raise InputError(f"{label}: a row has {len(cells)} cells, the header has {header_size}")
    return cells


def _body_rows(block: Sequence[tuple[int, str]], label: str) -> list[tuple[int, list[str]]]:
    """The rows below the header separator, each checked against the header's width.

    Each row keeps the line number it sits on, so a rejection can name the line a
    reader has to look at rather than only the file.
    """
    header_size = len(_cells(block[0][1]))
    return [(number, _parse_row(line, header_size, label)) for number, line in block[2:]]


def find_table_rows(source: str, columns: Sequence[str], label: str) -> list[tuple[int, list[str]]]:
    """The body rows of the first table whose leading headers are `columns`.

    The table is found by its column headers rather than by position, so a
    section added above it cannot make the guard read the wrong table. Each row
    is returned with its 1-based line number.
    """
    for block in _table_blocks(source):
        if _is_table_block(block, columns):
            return _body_rows(block, label)
    raise InputError(f"{label}: no table headed {' | '.join(columns)}")


def parse_baseline_table(
    source: str,
    capability_column: str,
    status_column: str,
    label: str,
) -> dict[str, str]:
    """The capability-to-status-cell rows of one baseline table."""
    rows = find_table_rows(source, (capability_column, status_column), label)
    names = [cells[0] for _, cells in rows]
    duplicated = next((name for name in names if names.count(name) > 1), None)
    if duplicated is not None:
        raise InputError(f"{label}: '{duplicated}' is listed twice")
    return {cells[0]: cells[1] for _, cells in rows}


def parse_docs_vocabulary(source: str) -> dict[str, str]:
    """The label-to-ledger-class map of the public status vocabulary table.

    A label listed twice is an input error rather than a later row replacing an
    earlier one. The table is read into a map, so a duplicate would keep the last
    class, drop the earlier one from the comparison, and leave both rows visible
    to a reader: a stale `IMPLEMENTED` row stating `provisional` above the correct
    row would make the guard report agreement between the surfaces.
    """
    rows = find_table_rows(source, ("Label", "Ledger class"), DOCS_LEDGER)
    vocabulary: dict[str, str] = {}
    listed_on: dict[str, int] = {}
    for number, cells in rows:
        label = DECORATION.sub("", cells[0])
        if label in listed_on:
            raise InputError(
                f"{DOCS_LEDGER}: label '{label}' is listed twice "
                f"(lines {listed_on[label]} and {number})"
            )
        listed_on[label] = number
        vocabulary[label] = DECORATION.sub("", cells[1])
    return vocabulary


def parse_status_union(source: str) -> list[str]:
    """The labels declared by `export type Status = 'A' | 'B' ...`."""
    match = STATUS_UNION.search(source)
    if match is None:
        raise InputError(f"{SITE_LEDGER}: no `export type Status` declaration")
    return re.findall(r"'([A-Z][A-Z_]*)'", match.group(1))


def parse_site_vocabulary(source: str) -> dict[str, str]:
    """The label-to-ledger-class map declared by `statusMeta`."""
    entries = list(META_ENTRY.finditer(source))
    if not entries:
        raise InputError(f"{SITE_LEDGER}: `statusMeta` declares no status")
    vocabulary: dict[str, str] = {}
    for index, match in enumerate(entries):
        end = entries[index + 1].start() if index + 1 < len(entries) else len(source)
        found = LEDGER_CLASS.search(source, match.end(), end)
        if found is None:
            raise InputError(f"{SITE_LEDGER}: statusMeta.{match.group(1)} has no ledgerClass")
        vocabulary[match.group(1)] = found.group(1)
    return vocabulary


def parse_site_rows(source: str) -> dict[str, str]:
    """The capability rows the site renders, name to status label.

    Every top-level element of `capabilityRows` is either compared or rejected;
    none is skipped. What is read is one single-quoted tuple per line, opening the
    line, with blank lines and `//` comments passed over. What is rejected, with an
    InputError naming the line, is every other shape: a spread of another
    `CapabilityRow[]` (`...someRows`), two entries sharing one line, an entry broken
    across lines, a double-quoted or backticked tuple, a template literal, a block
    comment, and an entry whose own strings carry a `[`.

    A skipped element was the hole: a spread renders on the site and never reached
    `compare_rows`, which is the check that every row belongs to a declared
    capability, so the guard reported agreement over rows it had not read.

    The entry format is rejected rather than widened, because widening only moves
    the same hole to the next form (a spread, a template literal, a single-quoted
    string carrying an escaped quote) while a rejected entry is a fact the guard
    can always state. `ledger.ts` is formatted with single quotes, one entry per
    line, so an entry in another form is also a deviation worth failing on.
    """
    block, first_line = _capability_block(source)
    rows = _capability_entries(block, first_line)
    if not rows:
        raise InputError(f"{SITE_LEDGER}: `capabilityRows` lists no capability")
    return _unique_entries(rows)


def _capability_block(source: str) -> tuple[str, int]:
    """The `capabilityRows` array text, and the line number its opening line sits on.

    The array runs from the line that opens it to the first line that closes it,
    so text after the array is not scanned for entries. The line number is carried
    so a rejected entry can name the line a reader has to look at.
    """
    start = source.find("const capabilityRows")
    if start == -1:
        raise InputError(f"{SITE_LEDGER}: no `capabilityRows` array")
    end = source.find("\n]", start)
    block = source[start:] if end == -1 else source[start:end]
    return block, source.count("\n", 0, start) + 1


def _capability_entries(block: str, first_line: int) -> list[tuple[str, str]]:
    """Every entry of `block`, parsed, with the line number it sits on.

    Every line is accounted for, because the three groups are exhaustive: the
    declaration line must end at its opening bracket, a blank line or a `//`
    comment holds no entry, and every other line must be exactly one entry. A
    line that matches none of them -- a spread, a second entry sharing a line, an
    entry broken across lines, a block comment -- is an InputError naming the
    line, never a line to pass over.
    """
    rows: list[tuple[str, str]] = []
    for offset, line in enumerate(block.splitlines()):
        number = first_line + offset
        if offset == 0:
            _check_declaration_line(line, number)
        elif _is_trivia(line):
            continue
        else:
            rows.append(_capability_row(line, number))
    return rows


def _check_declaration_line(line: str, number: int) -> None:
    """Require the `capabilityRows` declaration to end at its opening bracket.

    An entry sharing the declaration's line would be an entry no line reader ever
    sees, so it is rejected rather than read: one entry per line is the only
    layout the guard can account for.
    """
    if line.rstrip().endswith("["):
        return
    raise InputError(
        f"{SITE_LEDGER}: the capabilityRows declaration on line {number} must end at its "
        f"opening '[': {line.strip()}"
    )


def _is_trivia(line: str) -> bool:
    """Whether a line inside the array holds no entry: it is blank, or a `//` comment.

    A `/* */` block comment is not trivia here: skipping one needs multi-line
    state, and a line the reader cannot classify is rejected rather than guessed
    at, so it is reported with the message for an unreadable entry.
    """
    stripped = line.strip()
    return not stripped or stripped.startswith("//")


def _unique_entries(rows: Sequence[tuple[str, str]]) -> dict[str, str]:
    """The entries as a name-to-status map; a name listed twice is an InputError.

    The map keeps one status per name, so a duplicate would let a corrected row
    sit beside a stale one and leave the guard comparing whichever it read last.
    """
    names = [name for name, _ in rows]
    if len(set(names)) != len(names):
        raise InputError(f"{SITE_LEDGER}: `capabilityRows` lists a name twice")
    return dict(rows)


def _capability_row(line: str, number: int) -> tuple[str, str]:
    """The name and status of one `capabilityRows` entry, or an InputError naming it.

    The entry must be one single-quoted tuple that opens its line and ends it. The
    line is matched whole, so a second entry after the first on the same line is a
    rejection rather than a name-and-status pair read from the first and a second
    entry left uncounted. A `[` inside an entry's own strings is not supported for
    the same reason the other shapes are not: the reader cannot tell a bracket in a
    claim from the bracket that opens the next entry, so it rejects the line rather
    than guess which.
    """
    match = CAPABILITY_ROW.match(line)
    if match is None:
        raise InputError(
            f"{SITE_LEDGER}: the capabilityRows entry on line {number} cannot be read: "
            f"{line.strip()}"
        )
    name, status = match.groups()
    return name, status


def parse_vocabulary_list(source: str) -> list[str]:
    """The labels named by the bullet list of status labels."""
    labels = VOCABULARY_BULLET.findall(source)
    if not labels:
        raise InputError(f"{DOCS_VOCABULARY}: no `- **LABEL**` status list")
    return labels


# The kind of thing a finding is about: a status label or a capability. Every
# finding opens with one, so each is named once here instead of at every site
# that reports one.
LABEL_KIND = "label"
CAPABILITY_KIND = "capability"


def _finding(kind: str, name: str, detail: str) -> str:
    """A finding: what it is about, which one, and what disagrees."""
    return f"{kind} {name}: {detail}"


def _surfaces_without(label: str, surfaces: Mapping[str, set[str]]) -> list[str]:
    """The surfaces that do not name `label`."""
    return [name for name, names in surfaces.items() if label not in names]


def _missing_from_surfaces(
    declared: Sequence[str], surfaces: Mapping[str, set[str]]
) -> list[str]:
    """One finding per declared label a surface does not name."""
    problems: list[str] = []
    for label in sorted(set(declared)):
        absent = _surfaces_without(label, surfaces)
        if absent:
            problems.append(
                _finding(
                    LABEL_KIND,
                    label,
                    f"declared in `Status` but missing from {', '.join(absent)}",
                )
            )
    return problems


def _undeclared_labels(surfaces: Mapping[str, set[str]], declared: Sequence[str]) -> list[str]:
    """One finding per label a surface names that `Status` does not declare."""
    named = set().union(*surfaces.values())
    return [
        _finding(LABEL_KIND, label, "named by the docs but not declared in `Status`")
        for label in sorted(named - set(declared))
    ]


def _class_disagreements(
    declared: Sequence[str],
    site: Mapping[str, str],
    docs: Mapping[str, str],
) -> list[str]:
    """One finding per declared label whose ledger class differs between the two maps."""
    return [
        _finding(
            LABEL_KIND,
            label,
            f"ledger class '{site[label]}' in `statusMeta` but "
            f"'{docs[label]}' in the docs vocabulary table",
        )
        for label in sorted(set(declared) & set(site) & set(docs))
        if site[label] != docs[label]
    ]


def compare_vocabulary(
    declared: Sequence[str],
    site: Mapping[str, str],
    docs: Mapping[str, str],
    listed: Sequence[str],
) -> list[str]:
    """One finding per label whose presence or ledger class disagrees."""
    surfaces = {
        "`statusMeta`": set(site),
        "the docs vocabulary table": set(docs),
        "the concepts list": set(listed),
    }
    return [
        *_missing_from_surfaces(declared, surfaces),
        *_undeclared_labels(surfaces, declared),
        *_class_disagreements(declared, site, docs),
    ]


def read_status(cell: str, states_ledger_class: bool, vocabulary: Mapping[str, str]) -> str | None:
    """The declared label a status cell states, or None when it states none.

    A site surface writes the label; the engineering ledger writes a ledger class
    and its cell may name several, so the row status is the first one. Reading a
    label the vocabulary does not declare as `None` is deliberate: an unknown
    label is a finding, not a value to compare.
    """
    if not states_ledger_class:
        label = DECORATION.sub("", cell)
        return label if label in vocabulary else None
    tokens = CLASS_TOKEN.findall(cell)
    if not tokens:
        return None
    return next(
        (label for label, ledger_class in vocabulary.items() if ledger_class == tokens[0]),
        None,
    )


@dataclass(frozen=True)
class _Reading:
    """What is needed to turn one surface's status cell into a declared label."""

    rows_by_surface: Mapping[str, Mapping[str, str]]
    vocabulary: Mapping[str, str]
    class_surfaces: frozenset[str]

    def label(self, surface: str, cell: str) -> str | None:
        """The label the cell states, or None when it states none."""
        return read_status(cell, surface in self.class_surfaces, self.vocabulary)


def _stated_by_surface(
    reading: _Reading,
    capability: str,
    declared: Mapping[str, str | None],
) -> tuple[dict[str, str], list[str]]:
    """The label each surface states for `capability`, and the findings where it cannot."""
    stated: dict[str, str] = {}
    problems: list[str] = []
    for surface, name in declared.items():
        rows = reading.rows_by_surface.get(surface) if name is not None else None
        if rows is None:
            continue
        if name not in rows:
            problems.append(
                _finding(
                    CAPABILITY_KIND,
                    capability,
                    f"declared in {surface} as '{name}', but that surface has no such row",
                )
            )
            continue
        label = reading.label(surface, rows[name])
        if label is None:
            problems.append(
                _finding(
                    CAPABILITY_KIND,
                    capability,
                    f"{surface} states '{rows[name]}', which is not a declared status",
                )
            )
            continue
        stated[surface] = label
    return stated, problems


def compare_capabilities(
    rows_by_surface: Mapping[str, Mapping[str, str]],
    vocabulary: Mapping[str, str],
    class_surfaces: frozenset[str],
) -> list[str]:
    """One finding per capability whose status disagrees, or cannot be read."""
    reading = _Reading(rows_by_surface, vocabulary, class_surfaces)
    problems: list[str] = []
    for capability, declared in CAPABILITIES.items():
        stated, stated_problems = _stated_by_surface(reading, capability, declared)
        problems.extend(stated_problems)
        if len(set(stated.values())) > 1:
            problems.append(
                _finding(
                    CAPABILITY_KIND,
                    capability,
                    "; ".join(f"{surface} says {label}" for surface, label in stated.items()),
                )
            )
    return problems


def compare_rows(rows_by_surface: Mapping[str, Mapping[str, str]]) -> list[str]:
    """One finding per row that no declared capability accounts for."""
    declared = {
        (surface, name)
        for names in CAPABILITIES.values()
        for surface, name in names.items()
        if name is not None
    }
    return [
        f"{surface} lists '{name}', which no declared capability accounts for"
        for surface, rows in rows_by_surface.items()
        for name in rows
        if (surface, name) not in declared
    ]


def collect(root: Path) -> tuple[dict[str, dict[str, str]], dict[str, str], list[str]]:
    """Read every surface, returning its rows, the site vocabulary, and the findings."""
    sources = {
        relative: read(root, relative)
        for relative in {SITE_LEDGER, DOCS_LEDGER, DOCS_VOCABULARY}
        | {surface.path for surface in SURFACES}
    }
    site_source = sources[SITE_LEDGER]
    site_vocabulary = parse_site_vocabulary(site_source)

    rows_by_surface: dict[str, dict[str, str]] = {"ledger": parse_site_rows(site_source)}
    for surface in SURFACES:
        rows_by_surface[surface.key] = parse_baseline_table(
            sources[surface.path],
            surface.capability_column,
            surface.status_column,
            surface.path,
        )

    vocabulary_problems = compare_vocabulary(
        parse_status_union(site_source),
        site_vocabulary,
        parse_docs_vocabulary(sources[DOCS_LEDGER]),
        parse_vocabulary_list(sources[DOCS_VOCABULARY]),
    )
    return rows_by_surface, site_vocabulary, vocabulary_problems


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=ROOT, help="repository root")
    args = parser.parse_args(argv)

    try:
        rows_by_surface, site_vocabulary, vocabulary_problems = collect(args.root)
    except InputError as error:
        print(f"check-status-vocabulary: {error}", file=sys.stderr)
        return 2

    class_surfaces = frozenset(surface.key for surface in SURFACES if surface.states_ledger_class)
    problems = [
        *vocabulary_problems,
        *compare_capabilities(rows_by_surface, site_vocabulary, class_surfaces),
        *compare_rows(rows_by_surface),
    ]
    if problems:
        print(f"check-status-vocabulary: {len(problems)} disagreement(s)", file=sys.stderr)
        for problem in problems:
            print(f"  {problem}", file=sys.stderr)
        return 1
    print(
        "check-status-vocabulary: the four surfaces state one vocabulary and "
        "one status per capability"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
