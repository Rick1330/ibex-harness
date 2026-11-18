"""The declared status vocabulary in ``site/app/data/ledger.ts``.

``export type Status`` is the label set every surface must name, and ``statusMeta``
is the label-to-ledger-class map it must agree with. Both are read from the site
ledger because that module is where the site declares them; the guard never infers
the vocabulary from a surface that merely uses it.
"""

from __future__ import annotations

import re

from .contract import SITE_LEDGER, InputError
from .lexer import CODE, Lexer, line_number, module_match

STATUS_UNION = re.compile(r"export type Status = ([^\n]+)")
# `statusMeta` and the `{` of a direct object initializer on the same line. The
# initializer is checked because `statusMeta` must be the object, not a name or a
# call that resolves to a map declared elsewhere: reading properties out of the
# latter would describe a map this file may not even contain.
META_OBJECT = re.compile(
    r"^[ \t]*(?:export[ \t]+)?const[ \t]+statusMeta(?![$\w])[^=\n]*=[ \t]*\{", re.MULTILINE
)
META_ENTRY = re.compile(r"^ {2}([A-Z][A-Z_]*): \{$", re.MULTILINE)
LEDGER_CLASS = re.compile(r"ledgerClass: '([^']+)'")


def parse_status_union(source: str) -> list[str]:
    """The labels declared by `export type Status = 'A' | 'B' ...`."""
    match = STATUS_UNION.search(source)
    if match is None:
        raise InputError(f"{SITE_LEDGER}: no `export type Status` declaration")
    return re.findall(r"'([A-Z][A-Z_]*)'", match.group(1))


def parse_site_vocabulary(source: str) -> dict[str, str]:
    """The label-to-ledger-class map declared by `statusMeta`'s own properties.

    `ledgerClass` is read from the object of each `statusMeta` property and from
    nowhere else. A later object in the file holding an `IMPLEMENTED` entry is a
    different map, and reading it overwrote the live class -- the map said
    `provisional` while the guard compared `implemented`. A label `statusMeta` states
    twice, or a property stating two classes, cannot be attributed to the live map, so
    each is an InputError rather than whichever value the scan met last.
    """
    opening, closing = status_meta_body(source)
    entries = code_properties(source, META_ENTRY, opening, closing)
    if not entries:
        raise InputError(f"{SITE_LEDGER}: `statusMeta` declares no status")
    vocabulary: dict[str, str] = {}
    lines: dict[str, int] = {}
    for entry in entries:
        label = entry.group(1)
        number = line_number(source, entry.start())
        if label in lines:
            raise InputError(
                f"{SITE_LEDGER}: statusMeta states {label} twice "
                f"(lines {lines[label]} and {number})"
            )
        lines[label] = number
        vocabulary[label] = ledger_class(source, entry)
    return vocabulary


def status_meta_body(source: str) -> tuple[int, int]:
    """The indexes of the `{` and `}` of the `statusMeta` object, or an InputError.

    The declaration is found at module level, so a mention inside a comment, a string,
    or a function body is not read. The object's own closing brace bounds every read
    below it, which is what keeps a later object in the file out of the map.
    """
    match = module_match(source, META_OBJECT)
    if match is None:
        raise InputError(
            f"{SITE_LEDGER}: no `statusMeta` object declaration, so the label-to-class "
            "map cannot be attributed"
        )
    opening = match.end() - 1
    return opening, object_end(source, opening)


def object_end(source: str, opening: int) -> int:
    """The index of the `}` closing the object whose `{` sits at `opening`.

    Strings, comments, and templates are consumed whole, so a brace inside a label or
    a description neither opens nor closes a level and cannot end the object early.
    A construct the scan cannot follow -- a template that substitutes an expression, or
    a `/` it cannot classify -- is rejected by the `Lexer` instead of skipped.
    """
    lexer = Lexer()
    index = lexer.step(source, opening, len(source))
    while index < len(source):
        index = lexer.step(source, index, len(source))
        if lexer.depth == 0:
            return index - 1
    raise InputError(
        f"{SITE_LEDGER}: the object opened on line {line_number(source, opening)} is not closed"
    )


def ledger_class(source: str, entry: re.Match[str]) -> str:
    """The one `ledgerClass` the entry's own object states, or an InputError.

    The property is read in code position, so a class stated in a `//` or `/* */`
    comment is not the live value: the comment above the real one won before, and the
    guard compared a class the site does not use.
    """
    opening = entry.end() - 1
    found = code_properties(source, LEDGER_CLASS, opening, object_end(source, opening))
    if not found:
        raise InputError(f"{SITE_LEDGER}: statusMeta.{entry.group(1)} has no ledgerClass")
    if len(found) > 1:
        raise InputError(
            f"{SITE_LEDGER}: statusMeta.{entry.group(1)} states {len(found)} "
            "ledgerClass properties; it must state one"
        )
    return found[0].group(1)


def code_properties(
    source: str, pattern: re.Pattern[str], opening: int, closing: int
) -> list[re.Match[str]]:
    """The matches of `pattern` in code at the depth of the body opened at `opening`.

    The body is bounded by its own closing brace, and every candidate is read by one
    `Lexer`, in order: a property written inside a comment, a string, a nested object,
    or a later object in the file is not a property of this body.
    """
    lexer = Lexer()
    lexer.step(source, opening, len(source))
    depth = lexer.depth
    scanned = opening + 1
    found: list[re.Match[str]] = []
    for match in pattern.finditer(source, opening, closing):
        lexer.advance(source, scanned, match.start())
        scanned = match.start()
        if lexer.mode == CODE and lexer.depth == depth:
            found.append(match)
    return found
