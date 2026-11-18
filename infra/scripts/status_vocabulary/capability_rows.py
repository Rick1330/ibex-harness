"""The capability rows ``ledger.ts`` renders: find the array, read every entry.

The array is resolved before its entries are read, because comparing one array
while the site renders another is the hole this module exists to close: the
declaration is found at module level rather than by the first mention of the name,
only a direct array initializer is accepted, and nothing may follow the closing
``]`` that continues the initializer.

Every element between the brackets is either compared or rejected; none is
skipped. A skipped element would render on the site and never reach
``compare_rows``, so the guard would report agreement over rows it had not read.
"""

from __future__ import annotations

import re
from collections.abc import Sequence

from .contract import SITE_LEDGER, InputError
from .lexer import (
    Lexer,
    excerpt,
    line_end,
    line_number,
    lines_between,
    module_match,
    skip_string,
    skip_trivia,
    starts_trivia,
)

# The declaration, at statement position: the kind of binding must follow the line
# start, so a mention inside a comment is not taken for the declaration, and the name
# must be followed by something that cannot continue an ECMAScript identifier. `\b`
# matched between `s` and `$`, so `capabilityRows$archive` was accepted as the
# declaration and its rows were compared instead. See `capability_declaration`.
# The binding kind is captured because only `const` is read: see
# `capability_declaration`.
CAPABILITY_DECLARATION = re.compile(
    r"^[ \t]*(?:export[ \t]+)?(const|let|var)[ \t]+capabilityRows(?![$\w])", re.MULTILINE
)
# One entry: the name, the status, then the detail and href, whose text is not read.
# The bracket that ends the tuple is the first one on the line, so nothing may sit
# between the entry's closing `]` and the end of its line but a trailing comma:
# `], extraRow, // ]` -- an element hidden behind a bracket in the comment -- is
# rejected rather than half read.
CAPABILITY_ROW = re.compile(
    r"^\s*\[\s*'([^']+)'\s*,\s*'([A-Z][A-Z_]*)'\s*,[^\[\]]*\]\s*(?:,\s*)?$"
)


def parse_site_rows(source: str) -> dict[str, str]:
    """The capability rows the site renders, name to status label.

    Every top-level element of `capabilityRows` is either compared or rejected;
    none is skipped. What is read is one single-quoted tuple per line, opening the
    line, with blank lines and `//` comments passed over. What is rejected, with an
    InputError naming the line, is every other shape: a spread of another
    `CapabilityRow[]` (`...someRows`), two entries sharing one line, an entry broken
    across lines, a double-quoted or backticked tuple, a template literal, a block
    comment, an entry whose own strings carry a `[` or a `]`, and a line carrying a
    further element after the tuple.

    A skipped element was the hole: a spread renders on the site and never reached
    `compare_rows`, which is the check that every row belongs to a declared
    capability, so the guard reported agreement over rows it had not read.

    The array is resolved before its entries are read, because comparing one array
    while the site renders another is the same hole in a different place: the
    declaration is found at module level rather than by the first mention of the
    name, it must be a `const` binding, only a direct array initializer is accepted,
    and only whitespace or a `//` comment may follow the closing `]`. A token after
    that `]` which continues the initializer -- `[`, `(`, `.`, `?`, or a template
    literal, on the same line or the next -- is rejected for the same reason: the rows
    compared would not be the rows rendered.

    The entry format is rejected rather than widened, because widening only moves
    the same hole to the next form (a spread, a template literal, a single-quoted
    string carrying an escaped quote) while a rejected entry is a fact the guard
    can always state. `ledger.ts` is formatted with single quotes, one entry per
    line, so an entry in another form is also a deviation worth failing on.
    """
    opening, closing = capability_array(source)
    rows = capability_entries(source, opening, closing)
    if not rows:
        raise InputError(f"{SITE_LEDGER}: `capabilityRows` lists no capability")
    return unique_entries(rows)


def capability_array(source: str) -> tuple[int, int]:
    """The indexes of the `[` and `]` of `capabilityRows`, or an InputError.

    The declaration is located at statement position, so text above it mentioning
    the name is not taken for it. Only a direct array initializer is accepted:
    `rows ?? [ ... ]` renders `rows` when it is defined, so comparing the fallback
    would report agreement about an array the page does not use. The same holds for
    an initializer that is a name, a call, or a concatenation.
    """
    match = capability_declaration(source)
    number = line_number(source, match.start())
    closing_line = line_end(source, match.end())
    equals = first_code_token(source, match.end(), closing_line, "=")
    if equals == -1:
        raise InputError(
            f"{SITE_LEDGER}: the capabilityRows declaration on line {number} states no "
            "initializer on that line"
        )
    opening = skip_trivia(source, equals + 1)
    if source[opening : opening + 1] != "[":
        raise InputError(
            f"{SITE_LEDGER}: the capabilityRows declaration on line {number} must be a direct "
            f"array initializer, not '{excerpt(source[equals + 1 :])}'"
        )
    check_opening_tail(source, opening, number)
    closing = array_end(source, opening)
    check_array_tail(source, closing)
    return opening, closing


def capability_declaration(source: str) -> re.Match[str]:
    """The module-level `const` declaration of `capabilityRows`, not a mention of it.

    Searching for the name alone returned its first occurrence, which can sit inside
    a comment: a commented-out copy of the array above the real one would then be the
    array the guard compared, and its rows would never be the rows the site renders.

    The text before each candidate is read once, in order, by one `Lexer`, so the
    candidate is taken only when it is code and no scope is open. A helper that
    declares its own `capabilityRows` is skipped: the export reads the module-level
    binding, so comparing the local one would compare rows nothing renders.

    Only `const` is accepted. A `let` or `var` binding can be assigned again after the
    array -- `let capabilityRows = [ ... ]` then `capabilityRows = []` -- and the
    export reads the reassigned value, so the guard would compare the initial rows
    while the page renders none. Requiring `const` is the whole rule: a `let` holding
    a literal that never changes is not a shape worth reading, and the rejection names
    the line and the kind found.
    """
    match = module_match(source, CAPABILITY_DECLARATION)
    if match is None:
        raise InputError(f"{SITE_LEDGER}: no `capabilityRows` array")
    kind = match.group(1)
    if kind != "const":
        raise InputError(
            f"{SITE_LEDGER}: the capabilityRows declaration on line "
            f"{line_number(source, match.start())} is `{kind}`; it must be `const`, "
            "because a reassignable binding can be handed a different array after the "
            "one that was read"
        )
    return match


def first_code_token(source: str, start: int, end: int, wanted: str) -> int:
    """The first index of `wanted` in `source[start:end]` that is code, or -1.

    A plain `str.find` took an `=` inside a comment or a string for the assignment.
    `const capabilityRows /* = [ archived */ = [` then read the bracket inside the
    comment as the array, and `const capabilityRows // = [` accepted a declaration
    that assigns nothing at all -- the rows came from dead code below it. The token is
    found by the scan the declaration itself is found by.
    """
    lexer = Lexer()
    index = start
    while index < end:
        if lexer.module_level and source[index] == wanted:
            return index
        index = lexer.step(source, index, end)
    return -1


def check_opening_tail(source: str, opening: int, number: int) -> None:
    """Require the array's opening line to end at its opening `[`.

    A `[` inside a trailing comment -- `= oldRows // [` -- would satisfy a check that
    only looked at the line's last character, while the array itself opened earlier.
    The bracket is the one the scanner found, and only whitespace or a `//` comment
    may follow it: an entry sharing that line is an entry no line reader ever sees.
    """
    tail = source[opening + 1 : line_end(source, opening)].strip()
    if tail and not tail.startswith("//"):
        raise InputError(
            f"{SITE_LEDGER}: the capabilityRows declaration on line {number} must end at its "
            f"opening '[': {excerpt(tail)}"
        )


def check_array_tail(source: str, closing: int) -> None:
    """Reject anything after the array's closing `]` but whitespace or a `//` comment.

    A trailing operation -- `.map(...)`, `.concat(...)`, `.filter(...)`, `.flat()`,
    `as const`, `['filter'](...)`, `(...)` -- hands the site rows this text does not
    contain, so the comparison would cover a different array than the page renders. It
    is rejected rather than evaluated, because evaluating it means interpreting
    TypeScript. A `;` is rejected by the same rule: `ledger.ts` is written without
    statement terminators, so one appearing here is a form the guard does not read.
    """
    number = line_number(source, closing)
    tail = source[closing + 1 : line_end(source, closing + 1)].strip()
    following = skip_trivia(source, closing + 1)
    if tail_is_code(tail) or next_is_operation(source, following):
        raise InputError(
            f"{SITE_LEDGER}: the capabilityRows array ending on line {number} must end at "
            f"its ']', but '{excerpt(source[following:])}' follows it"
        )


def tail_is_code(tail: str) -> bool:
    """Whether the rest of the `]` line is anything but a `//` comment."""
    return bool(tail) and not tail.startswith("//")


def next_is_operation(source: str, index: int) -> bool:
    """Whether the token at `index` continues the array's initializer.

    TypeScript does not end a statement at a line break, so a `]` followed by `.`,
    `[`, `(`, `?`, or a template literal is one expression: `.map(...)`,
    `['filter'](row => ...)`, `?.map(...)`, `` ]`...` ``. Each hands the site rows this
    text does not contain -- a filter drops a row, an index reads a different one --
    so the comparison would cover an array the page never renders. `?` is included
    because `]` followed by `?.` is optional chaining, which is the same continuation
    as `.`; only `.` was checked, and `['filter'](...)` on the next line was accepted.
    """
    return source[index : index + 1] in (".", "[", "(", "`", "?")


def capability_entries(source: str, opening: int, closing: int) -> list[tuple[str, str]]:
    """Every entry between the brackets, parsed, with the line number it sits on.

    Every line is accounted for, because the two groups are exhaustive: a blank line
    or a `//` comment holds no entry, and every other line must be exactly one entry.
    A line that matches neither -- a spread, a second entry sharing a line, an entry
    broken across lines, a block comment -- is an InputError naming the line, never a
    line to pass over.
    """
    return [
        capability_row(line, number)
        for number, line in lines_between(source, opening + 1, closing)
        if not is_trivia(line)
    ]


def is_trivia(line: str) -> bool:
    """Whether a line inside the array holds no entry: it is blank, or a `//` comment.

    A `/* */` block comment is not trivia here: skipping one needs multi-line
    state, and a line the reader cannot classify is rejected rather than guessed
    at, so it is reported with the message for an unreadable entry.
    """
    stripped = line.strip()
    return not stripped or stripped.startswith("//")


def unique_entries(rows: Sequence[tuple[str, str]]) -> dict[str, str]:
    """The entries as a name-to-status map; a name listed twice is an InputError.

    The map keeps one status per name, so a duplicate would let a corrected row
    sit beside a stale one and leave the guard comparing whichever it read last.
    """
    names = [name for name, _ in rows]
    if len(set(names)) != len(names):
        raise InputError(f"{SITE_LEDGER}: `capabilityRows` lists a name twice")
    return dict(rows)


def capability_row(line: str, number: int) -> tuple[str, str]:
    """The name and status of one `capabilityRows` entry, or an InputError naming it.

    The entry must be one single-quoted tuple that opens its line and ends it. The
    line is matched whole, so a second entry after the first on the same line is a
    rejection rather than a name-and-status pair read from the first and a second
    entry left uncounted. A `[` or `]` inside an entry's own strings is not supported
    for the same reason the other shapes are not: the reader cannot tell a bracket in
    a claim from the bracket that ends the tuple, so it rejects the line rather than
    guess which. The bracket that ends the tuple is the first one on the line, so
    `['X', 'A', 'd', '/y'], extraRow, // ]` -- an element hidden behind a bracket in
    the trailing comment -- leaves that element visible to the reader and rejected
    here rather than compared as a single row.
    """
    match = CAPABILITY_ROW.match(line)
    if match is None:
        raise InputError(
            f"{SITE_LEDGER}: the capabilityRows entry on line {number} cannot be read: "
            f"{line.strip()}"
        )
    name, status = match.groups()
    return name, status


def array_end(source: str, opening: int) -> int:
    """The index of the `]` that closes the array opened at `opening`.

    Strings and comments are skipped, so a `]` inside a rendered detail or inside a
    commented-out row neither ends the array early nor leaves entries unread. Each
    turn of the loop hands one token to `array_step`, which classifies it and says
    where the scan resumes and what it did to the depth.
    """
    depth = 0
    index = opening
    closed = False
    while index < len(source) and not closed:
        index, depth, closed = array_step(source, index, depth)
    if not closed:
        raise InputError(f"{SITE_LEDGER}: the `capabilityRows` array is not closed")
    return index


def array_step(source: str, index: int, depth: int) -> tuple[int, int, bool]:
    """Consume what begins at `index`: the index to resume at, the depth, and closure.

    A string and a comment are consumed whole, so a `]` inside a rendered detail or
    inside a commented-out row is not taken for the array's own bracket.
    """
    if source[index] in "'\"`":
        return skip_string(source, index), depth, False
    if starts_trivia(source, index):
        return skip_trivia(source, index), depth, False
    return bracket_step(source[index], index, depth)


def bracket_step(character: str, index: int, depth: int) -> tuple[int, int, bool]:
    """Consume one ordinary character, or the bracket that opens or closes a level."""
    if character == "[":
        return index + 1, depth + 1, False
    if character == "]":
        return close_level(index, depth)
    return index + 1, depth, False


def close_level(index: int, depth: int) -> tuple[int, int, bool]:
    """The step for a `]`: the level it leaves, and whether that level was the array's.

    The index stays on the `]` when the array closes, because that bracket is the
    index `array_end` returns; a `]` that only ends a nested array resumes after
    itself. A `]` before the array's own opening leaves a negative depth, which no
    later `]` returns to zero, so the array reads as unclosed -- the outcome the
    depth had when it was allowed to go negative.
    """
    remaining = depth - 1
    if remaining == 0:
        return index, remaining, True
    return index + 1, remaining, False
