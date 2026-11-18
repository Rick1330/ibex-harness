"""A forward scan of TypeScript text: comment state, string state, and scope depth.

The scan is the guard's only model of the language. It reads the text once, in
order, so a delimiter inside another construct stays that construct's text, and it
answers two questions: is the position in code, and how many braces are open. The
line, trivia, and string helpers below it are the same model applied to a range,
so the capability-row reader never splits a line or skips a comment on its own.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from .contract import SITE_LEDGER, InputError

# A TypeScript line ends at an ECMAScript line terminator: LF, CR, CRLF, U+2028 LINE
# SEPARATOR, or U+2029 PARAGRAPH SEPARATOR. `str.splitlines` also splits on a form
# feed, a vertical tab, and U+0085, which are whitespace but not terminators: a split
# there cuts the tail off a `//` comment and reads it as an array entry. Omitting
# U+2028 and U+2029 splits nothing where the language does, which keeps a live entry
# inside the comment. See `lines_between`.
TS_LINE_BREAK = re.compile(r"\r\n|[\r\n\u2028\u2029]")


# What a `Lexer` scan is inside: code, a `//` comment, a `/* */` comment, a quoted
# string, or a template literal. Only code holds a declaration.
CODE, LINE_COMMENT, BLOCK_COMMENT, STRING, TEMPLATE = "code", "line", "block", "string", "template"


@dataclass
class Lexer:
    """A forward scan of TypeScript text: comment state, string state, and scope depth.

    Counting `/*` and `*/` occurrences is not the same as tracking a comment: a `//`
    comment ending in `*/` was counted as a block closer, so a block-commented copy of
    the array below it looked live and its rows were compared. The scan reads the text
    once, in order, so a delimiter inside another construct stays that construct's
    text.

    Only `{` and `}` count as depth, because they are the only brackets that open a
    scope a declaration can sit in: a `const` inside `(` or `[` is not valid
    TypeScript, while a function body, an arrow body, a class body, and a bare block
    all open a `{`. Comment and string text is not code, so it changes neither the
    mode nor the depth.

    A template literal is skipped as text, but one that substitutes an expression is
    rejected: `${...}` is code that can open a scope, and reading it honestly would
    make this guard the TypeScript interpreter it is deliberately not.
    """

    mode: str = CODE
    quote: str = ""
    depth: int = 0

    @property
    def module_level(self) -> bool:
        """Whether the scan is in code, outside every scope."""
        return self.mode == CODE and self.depth == 0

    def advance(self, source: str, start: int, end: int) -> None:
        """Read `source[start:end]` into the state."""
        index = start
        while index < end:
            index = self.step(source, index, end)

    def step(self, source: str, index: int, end: int) -> int:
        """Consume the construct at `index` and return where the scan resumes."""
        if self.mode == LINE_COMMENT:
            return self._leave_line_comment(source, index, end)
        if self.mode == BLOCK_COMMENT:
            return self._leave_block_comment(source, index, end)
        if self.mode == STRING:
            return self._leave_string(source, index)
        if self.mode == TEMPLATE:
            return self._leave_template(source, index)
        return self._code_step(source, index)

    def _leave_line_comment(self, source: str, index: int, end: int) -> int:
        """Leave a `//` comment at the next line terminator, or stay in it."""
        found = TS_LINE_BREAK.search(source, index, end)
        if found is None:
            return end
        self.mode = CODE
        return found.end()

    def _leave_block_comment(self, source: str, index: int, end: int) -> int:
        """Leave a `/* */` comment past its terminator, or stay in it."""
        close = source.find("*/", index, end)
        if close == -1:
            return end
        self.mode = CODE
        return close + 2

    def _leave_string(self, source: str, index: int) -> int:
        """Leave a quoted string past its quote, or fail on one that never closes."""
        if source[index] == "\\":
            return index + 2
        if source[index] == self.quote:
            self.mode = CODE
            return index + 1
        if TS_LINE_BREAK.match(source, index):
            raise InputError(
                f"{SITE_LEDGER}: the string literal on line {line_number(source, index)} "
                "is not closed on its line"
            )
        return index + 1

    def _leave_template(self, source: str, index: int) -> int:
        """Skip template text, or fail on a substitution the scan cannot follow."""
        if source[index] == "\\":
            return index + 2
        if source[index] == "`":
            self.mode = CODE
            return index + 1
        if source.startswith("${", index):
            raise InputError(
                f"{SITE_LEDGER}: the template literal on line {line_number(source, index)} "
                "substitutes an expression, which is not read, so the capabilityRows "
                "declaration cannot be placed"
            )
        return index + 1

    def _code_step(self, source: str, index: int) -> int:
        """Read one token of code: the start of a comment, string, or template, or a brace."""
        if source.startswith("//", index):
            self.mode = LINE_COMMENT
            return index + 2
        if source.startswith("/*", index):
            self.mode = BLOCK_COMMENT
            return index + 2
        character = source[index]
        if character in "'\"":
            self.mode, self.quote = STRING, character
            return index + 1
        if character == "`":
            self.mode = TEMPLATE
            return index + 1
        if character == "{":
            self.depth += 1
        elif character == "}":
            self.depth = max(self.depth - 1, 0)
        return index + 1


def line_number(source: str, index: int) -> int:
    """The 1-based line `index` sits on, counting only TypeScript's terminators."""
    return len(TS_LINE_BREAK.findall(source, 0, index)) + 1


def line_end(source: str, index: int) -> int:
    """The index of the first TypeScript line terminator at or after `index`."""
    found = TS_LINE_BREAK.search(source, index)
    return len(source) if found is None else found.start()


def lines_between(source: str, start: int, end: int) -> list[tuple[int, str]]:
    """The lines of `source` from `start` to `end`, each with its 1-based number.

    Only TypeScript's terminators split the text. `str.splitlines` also splits on a
    form feed, a vertical tab, U+2028, U+0085 and others, so `// retired\\f['X', ...]`
    would become a comment line and an entry line -- while TypeScript keeps both in
    one comment -- and the guard would report agreement about a row nothing renders.
    """
    first = line_number(source, start)
    return [
        (first + offset, line)
        for offset, line in enumerate(TS_LINE_BREAK.split(source[start:end]))
    ]


def skip_trivia(source: str, index: int) -> int:
    """The first index at or after `index` that is neither whitespace nor a comment."""
    while index < len(source) and starts_trivia(source, index):
        index = end_of_trivia(source, index)
    return index


def starts_trivia(source: str, index: int) -> bool:
    """Whether trivia -- whitespace or a comment -- begins at `index`."""
    return source[index].isspace() or source.startswith(("//", "/*"), index)


def end_of_trivia(source: str, index: int) -> int:
    """The first index past the one run of trivia that begins at `index`.

    Called where `starts_trivia` holds, so the three kinds it names are exhaustive:
    a run of whitespace, a `//` comment to the end of its line, and a `/* ... */`
    comment to the end of its terminator.
    """
    if source[index].isspace():
        return end_of_whitespace(source, index)
    if source.startswith("//", index):
        return line_end(source, index)
    return end_of_block_comment(source, index)


def end_of_whitespace(source: str, index: int) -> int:
    """The first index at or after `index` that is not whitespace."""
    while index < len(source) and source[index].isspace():
        index += 1
    return index


def end_of_block_comment(source: str, index: int) -> int:
    """The index just past the `*/` that closes the `/*` comment opening at `index`."""
    close = source.find("*/", index + 2)
    if close == -1:
        raise InputError(f"{SITE_LEDGER}: an unterminated `/* ... */` comment")
    return close + 2


def skip_string(source: str, index: int) -> int:
    """The index just past the string literal that opens at `index`."""
    quote = source[index]
    index += 1
    while index < len(source):
        if source[index] == "\\":
            index += 2
        elif source[index] == quote:
            return index + 1
        else:
            index += 1
    raise InputError(f"{SITE_LEDGER}: an unterminated string literal in `capabilityRows`")


def excerpt(text: str) -> str:
    """The first line of `text`, stripped and shortened, for a rejection message."""
    line = TS_LINE_BREAK.split(text.strip(), maxsplit=1)[0]
    return line if len(line) <= 60 else f"{line[:57]}..."
