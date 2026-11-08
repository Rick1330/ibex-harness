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


def _parse(raw: str) -> str:
    value = raw.strip()
    if value[:1] in ("'", '"'):
        end = value.find(value[0], 1)
        return value[1:end] if end != -1 else value[1:]
    comment = _comment_start(value)
    return value[:comment].strip() if comment != -1 else value


def _lookup(expression: str, seen: dict[str, str]) -> str:
    name, separator, default = expression.partition(":-")
    if not separator:
        name, separator, default = expression.partition("-")
    name = name.strip()
    if name in seen:
        return seen[name]
    if name in os.environ:
        return os.environ[name]
    return default if separator else ""


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
        values[name] = _interpolate(_parse(rest), values)
    return values.get(key, "")


def main(argv: list[str]) -> int:
    if len(argv) != 2:
        print("usage: dotenv.py <key> < .env", file=sys.stderr)
        return 2
    print(read_value(sys.stdin, argv[1]))
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
