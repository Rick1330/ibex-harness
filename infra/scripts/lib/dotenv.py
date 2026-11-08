"""Read one value from a Docker Compose ``.env`` stream.

Compose has specific rules, and a naive "split on the first `=`" reader gets
them wrong in ways that break the profile:

* the last assignment for a key wins, because that is the value Compose exports;
* an unquoted value ends at the first whitespace followed by ``#``;
* a quoted value is taken between matching quotes, so ``#`` inside it is data;
* surrounding whitespace is ignored.

Usage: ``python3 dotenv.py <key> < .env`` prints the value (empty when absent).
Reading standard input keeps this helper free of path handling: the caller
already owns the file descriptor.
"""

from __future__ import annotations

import sys


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


def _assignment(raw: str):
    line = raw.strip()
    if not line or line.startswith("#"):
        return None
    name, separator, rest = line.partition("=")
    if not separator:
        return None
    return name.strip(), rest


def read_value(lines, key: str) -> str:
    value = ""
    for raw in lines:
        assignment = _assignment(raw)
        if assignment is None:
            continue
        name, rest = assignment
        if name == key:
            value = _parse(rest)
    return value


def main(argv: list[str]) -> int:
    if len(argv) != 2:
        print("usage: dotenv.py <key> < .env", file=sys.stderr)
        return 2
    print(read_value(sys.stdin, argv[1]))
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
