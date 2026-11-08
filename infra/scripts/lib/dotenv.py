"""Read one value from a Docker Compose ``.env`` file.

Compose has specific rules, and a naive "split on the first `=`" reader gets
them wrong in ways that break the profile:

* the last assignment for a key wins, because that is the value Compose exports;
* an unquoted value ends at the first whitespace followed by ``#``;
* a quoted value is taken between matching quotes, so ``#`` inside it is data;
* surrounding whitespace is ignored.

Usage: ``python3 dotenv.py <path> <key>`` prints the value (empty when absent).
"""

from __future__ import annotations

import re
import sys


def _parse(raw: str) -> str:
    value = raw.strip()
    if value[:1] in ("'", '"'):
        quote = value[0]
        end = value.find(quote, 1)
        if end != -1:
            return value[1:end]
        return value[1:]
    comment = re.search(r"\s+#", value)
    if comment:
        value = value[: comment.start()]
    return value.strip()


def read_value(path: str, key: str) -> str:
    pattern = re.compile(r"^\s*" + re.escape(key) + r"\s*=\s*(.*)$")
    value = ""
    try:
        with open(path, encoding="utf-8") as handle:
            for line in handle:
                match = pattern.match(line.rstrip("\n"))
                if match:
                    value = _parse(match.group(1))
    except FileNotFoundError:
        return ""
    return value


def main(argv: list[str]) -> int:
    if len(argv) != 3:
        print("usage: dotenv.py <path> <key>", file=sys.stderr)
        return 2
    print(read_value(argv[1], argv[2]))
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
