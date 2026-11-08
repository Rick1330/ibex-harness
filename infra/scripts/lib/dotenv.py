"""Read one value from a Docker Compose ``.env`` stream.

Compose has specific rules, and a naive "split on the first `=`" reader gets
them wrong in ways that break the profile:

* an optional ``export `` prefix is ignored;
* the last assignment for a key wins, because that is the value Compose exports;
* an unquoted value ends at the first whitespace followed by ``#``;
* a quoted value is taken between matching quotes, so ``#`` inside it is data;
* unquoted and quoted values are interpolated: ``$NAME``, ``${NAME}``,
  ``${NAME:-default}`` and ``${NAME-default}`` resolve against earlier
  assignments and the process environment, and ``$$`` is a literal ``$``.

Usage: ``python3 dotenv.py <key> < .env`` prints the value (empty when absent).
Reading standard input keeps this helper free of path handling: the caller
already owns the file descriptor.
"""

from __future__ import annotations

import os
import string
import sys


class DotenvError(ValueError):
    """A Compose-style required-variable substitution failed."""

NAME_CHARS = frozenset(string.ascii_letters + string.digits + "_")


def _comment_start(value: str) -> int:
    index = 0
    while True:
        index = value.find("#", index)
        if index == -1:
            return -1
        if index > 0 and value[index - 1].isspace():
            return index
        index += 1


def _closing_quote(value: str, quote: str) -> int:
    index = 1
    while index < len(value):
        if value[index] == "\\":
            index += 2
            continue
        if value[index] == quote:
            return index
        index += 1
    return -1


def _unescape(value: str) -> str:
    out: list[str] = []
    index = 0
    while index < len(value):
        if value[index] == "\\" and index + 1 < len(value):
            out.append(value[index + 1])
            index += 2
            continue
        out.append(value[index])
        index += 1
    return "".join(out)


def _parse(raw: str) -> tuple[str, str | None]:
    """Return the value and its quote style, if any.

    Single quotes are literal: Compose neither strips comments nor interpolates
    inside them. Double quotes are taken between matching quotes, honour escaped
    quotes, and are still interpolated.
    """
    value = raw.strip()
    if value.startswith("'"):
        end = _closing_quote(value, "'")
        return (value[1:end] if end != -1 else value[1:]), "'"
    if value.startswith('"'):
        end = _closing_quote(value, '"')
        return _unescape(value[1:end] if end != -1 else value[1:]), '"'
    comment = _comment_start(value)
    return (value[:comment].strip() if comment != -1 else value), None


def _default_if_empty(value, operand: str) -> str:
    return value if value else operand


def _default_if_unset(value, operand: str) -> str:
    return value if value is not None else operand


def _required_if_empty(value, operand: str) -> str:
    if not value:
        raise DotenvError(operand or "required variable is empty or unset")
    return value


def _required_if_unset(value, operand: str) -> str:
    if value is None:
        raise DotenvError(operand or "required variable is unset")
    return value


def _alternate_if_empty(value, operand: str) -> str:
    return operand if value else ""


def _alternate_if_unset(value, operand: str) -> str:
    return operand if value is not None else ""


# Order matters: the colon forms are matched before their plain counterparts.
OPERATOR_FUNCS = {
    ":-": _default_if_empty,
    "-": _default_if_unset,
    ":?": _required_if_empty,
    "?": _required_if_unset,
    ":+": _alternate_if_empty,
    "+": _alternate_if_unset,
}


def _split_operator(expression: str) -> tuple[str, str | None, str]:
    expr = expression.strip()
    end = _name_end(expr, 0)
    if end == 0:
        return "", None, ""
    name, rest = expr[:end], expr[end:]
    for operator in OPERATOR_FUNCS:
        if rest.startswith(operator):
            return name, operator, rest[len(operator) :]
    return name, None, ""


def _lookup(expression: str, seen: dict[str, str]) -> str:
    name, operator, operand = _split_operator(expression)
    if not name:
        return ""
    value = os.environ[name] if name in os.environ else seen.get(name)
    if operator is None:
        return value or ""
    return OPERATOR_FUNCS[operator](value, operand)


def _name_end(value: str, start: int) -> int:
    end = start
    while end < len(value) and value[end] in NAME_CHARS:
        end += 1
    return end


def _expand_braced(value: str, index: int, seen: dict[str, str], out: list[str]) -> int:
    end = value.find("}", index + 2)
    if end == -1:
        out.append(value[index:])
        return len(value)
    out.append(_lookup(value[index + 2 : end], seen))
    return end + 1


def _expand(value: str, index: int, seen: dict[str, str], out: list[str]) -> int:
    following = value[index + 1 : index + 2]
    if following == "$":
        out.append("$")
        return index + 2
    if following == "{":
        return _expand_braced(value, index, seen, out)
    end = _name_end(value, index + 1)
    if end == index + 1:
        out.append("$")
        return index + 1
    out.append(_lookup(value[index + 1 : end], seen))
    return end


def _interpolate(value: str, seen: dict[str, str]) -> str:
    out: list[str] = []
    index = 0
    while index < len(value):
        if value[index] == "$":
            index = _expand(value, index, seen, out)
            continue
        out.append(value[index])
        index += 1
    return "".join(out)


def _assignment(raw: str):
    line = raw.strip()
    if not line or line.startswith("#"):
        return None
    if line.startswith("export "):
        line = line[len("export ") :].lstrip()
    name, separator, rest = line.partition("=")
    if not separator:
        return None
    return name.strip(), rest


def read_value(lines, key: str) -> str:
    values: dict[str, str] = {}
    for raw in lines:
        assignment = _assignment(raw)
        if assignment is None:
            continue
        name, rest = assignment
        parsed, quote = _parse(rest)
        values[name] = parsed if quote == "'" else _interpolate(parsed, values)
    return values.get(key, "")


def main(argv: list[str]) -> int:
    if len(argv) != 2:
        print("usage: dotenv.py <key> < .env", file=sys.stderr)
        return 2
    try:
        print(read_value(sys.stdin, argv[1]))
    except DotenvError as error:
        print(f"dotenv: {error}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
