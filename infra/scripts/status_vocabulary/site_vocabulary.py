"""The declared status vocabulary in ``site/app/data/ledger.ts``.

``export type Status`` is the label set every surface must name, and ``statusMeta``
is the label-to-ledger-class map it must agree with. Both are read from the site
ledger because that module is where the site declares them; the guard never infers
the vocabulary from a surface that merely uses it.
"""

from __future__ import annotations

import re

from .contract import SITE_LEDGER, InputError

STATUS_UNION = re.compile(r"export type Status = ([^\n]+)")
META_ENTRY = re.compile(r"^ {2}([A-Z][A-Z_]*): \{$", re.MULTILINE)
LEDGER_CLASS = re.compile(r"ledgerClass: '([^']+)'")


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
