"""The markdown surfaces: pipe tables, the baseline table, and the docs lists.

A surface is found by its column headers rather than by position, so a section
added above it cannot make the guard read the wrong table. Every row is checked
against the header's width, and a duplicate is an input error rather than a later
row replacing an earlier one: a row the reader cannot place must fail, never be
dropped from the comparison while it stays visible to a reader.
"""

from __future__ import annotations

import re
from collections.abc import Iterable, Sequence

from .contract import DOCS_LEDGER, DOCS_VOCABULARY, InputError

SEPARATOR_CELL = re.compile(r"^:?-{3,}:?$")
CELL_SPLIT = re.compile(r"(?<!\\)\|")
DECORATION = re.compile(r"[`\s]")
VOCABULARY_BULLET = re.compile(r"^[-*]\s+\*\*([A-Z][A-Z_]*)\*\*", re.MULTILINE)


def undecorate(cell: str) -> str:
    """A table cell without the backticks and whitespace markdown may wrap it in."""
    return DECORATION.sub("", cell)


def cells(line: str) -> list[str]:
    return [cell.strip() for cell in CELL_SPLIT.split(line.strip().strip("|"))]


def is_separator(line: str) -> bool:
    found = cells(line)
    return bool(found) and all(SEPARATOR_CELL.match(cell) for cell in found)


def is_table_row(line: str) -> bool:
    """Whether `line` is a row of a GFM pipe table.

    GFM makes the leading and trailing pipes optional, so a line written as
    `Memory substrate | IMPLEMENTED | Hosted HA.` is a row of the table above it. The
    reader used to require both outer pipes, so such a row ended the block before it
    and went uncompared while a reader still saw it. A line carrying no `|` is not a
    row, which is what keeps prose between two tables from joining them; a line that
    does carry one but is not as wide as the header is rejected by `parse_row` rather
    than dropped.
    """
    return "|" in line


def table_blocks(source: str) -> Iterable[list[tuple[int, str]]]:
    """Every run of consecutive pipe-table lines, each line with its 1-based number."""
    block: list[tuple[int, str]] = []
    for number, line in enumerate(source.splitlines(), start=1):
        if is_table_row(line):
            block.append((number, line))
            continue
        if block:
            yield block
            block = []
    if block:
        yield block


def is_table_block(block: Sequence[tuple[int, str]], columns: Sequence[str]) -> bool:
    """Whether a block's first two lines are the header of a table of `columns`."""
    if len(block) < 2 or not is_separator(block[1][1]):
        return False
    return cells(block[0][1])[: len(columns)] == list(columns)


def parse_row(line: str, header_size: int, label: str) -> list[str]:
    """A table row as cells, or an InputError when it is not as wide as the header.

    A mis-split row would move a status into the capability column and compare
    prose, so a width mismatch is an input error rather than a row to keep.
    """
    found = cells(line)
    if len(found) != header_size:
        raise InputError(f"{label}: a row has {len(found)} cells, the header has {header_size}")
    return found


def body_rows(block: Sequence[tuple[int, str]], label: str) -> list[tuple[int, list[str]]]:
    """The rows below the header separator, each checked against the header's width.

    Each row keeps the line number it sits on, so a rejection can name the line a
    reader has to look at rather than only the file.
    """
    header_size = len(cells(block[0][1]))
    return [(number, parse_row(line, header_size, label)) for number, line in block[2:]]


def find_table_rows(
    source: str, columns: Sequence[str], label: str
) -> list[tuple[int, list[str]]]:
    """The body rows of the first table whose leading headers are `columns`.

    The table is found by its column headers rather than by position, so a
    section added above it cannot make the guard read the wrong table. Each row
    is returned with its 1-based line number.
    """
    for block in table_blocks(source):
        if is_table_block(block, columns):
            return body_rows(block, label)
    raise InputError(f"{label}: no table headed {' | '.join(columns)}")


def parse_baseline_table(
    source: str,
    capability_column: str,
    status_column: str,
    label: str,
) -> dict[str, str]:
    """The capability-to-status-cell rows of one baseline table."""
    rows = find_table_rows(source, (capability_column, status_column), label)
    names = [row[0] for _, row in rows]
    duplicated = next((name for name in names if names.count(name) > 1), None)
    if duplicated is not None:
        raise InputError(f"{label}: '{duplicated}' is listed twice")
    return {row[0]: row[1] for _, row in rows}


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
    for number, row in rows:
        label = undecorate(row[0])
        if label in listed_on:
            raise InputError(
                f"{DOCS_LEDGER}: label '{label}' is listed twice "
                f"(lines {listed_on[label]} and {number})"
            )
        listed_on[label] = number
        vocabulary[label] = undecorate(row[1])
    return vocabulary


def parse_vocabulary_list(source: str) -> list[str]:
    """The labels named by the bullet list of status labels."""
    labels = VOCABULARY_BULLET.findall(source)
    if not labels:
        raise InputError(f"{DOCS_VOCABULARY}: no `- **LABEL**` status list")
    return labels
