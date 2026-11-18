"""Read every surface once, so the comparison has something to compare.

A missing or unreadable file is an ``InputError`` rather than an empty surface: a
surface the guard cannot read must fail, because reporting agreement over data it
never read is the failure mode this whole check exists to prevent.
"""

from __future__ import annotations

from pathlib import Path

from .capability_rows import parse_site_rows
from .compare import compare_vocabulary
from .contract import DOCS_LEDGER, DOCS_VOCABULARY, SITE_LEDGER, SURFACES, InputError
from .site_vocabulary import parse_site_vocabulary, parse_status_union
from .tables import parse_baseline_table, parse_docs_vocabulary, parse_vocabulary_list


def read(root: Path, relative: str) -> str:
    """The text of a repository file, or an InputError naming what is missing."""
    try:
        return (root / relative).read_text(encoding="utf-8")
    except OSError as error:
        raise InputError(f"{relative}: {error}") from error


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
