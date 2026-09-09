#!/usr/bin/env python3
"""Merge Go cover profiles without pulling golang.org/x/tools (Go 1.26+).

Compatible with github.com/wadey/gocovmerge semantics for mode set/count/atomic.
"""

from __future__ import annotations

import sys
from pathlib import Path


def _merge(paths: list[Path]) -> tuple[str, dict[str, tuple[int, int]]]:
    mode: str | None = None
    blocks: dict[str, tuple[int, int]] = {}
    for path in paths:
        lines = path.read_text(encoding="utf-8").splitlines()
        if not lines or not lines[0].startswith("mode:"):
            raise SystemExit(f"bad cover profile (missing mode): {path}")
        file_mode = lines[0].split(":", 1)[1].strip()
        if mode is None:
            mode = file_mode
        elif mode != file_mode:
            raise SystemExit(f"mode mismatch: {mode} vs {file_mode} ({path})")
        for line in lines[1:]:
            line = line.strip()
            if not line:
                continue
            key, stmts_s, count_s = line.rsplit(" ", 2)
            stmts = int(stmts_s)
            count = int(count_s)
            if key in blocks:
                prev_stmts, prev_count = blocks[key]
                if prev_stmts != stmts:
                    raise SystemExit(f"statement count mismatch for {key}")
                if mode == "set":
                    count = prev_count or count
                else:
                    count = prev_count + count
            blocks[key] = (stmts, count)
    if mode is None:
        raise SystemExit("no cover profiles provided")
    return mode, blocks


def main(argv: list[str]) -> int:
    if len(argv) < 3:
        print(
            f"usage: {argv[0]} <out.out> <profile1.out> [profile2.out ...]",
            file=sys.stderr,
        )
        return 2
    out = Path(argv[1])
    profiles = [Path(p) for p in argv[2:]]
    for path in profiles:
        if not path.is_file():
            raise SystemExit(f"cover profile not found: {path}")
    mode, blocks = _merge(profiles)
    lines = [f"mode: {mode}\n"]
    for key in sorted(blocks):
        stmts, count = blocks[key]
        lines.append(f"{key} {stmts} {count}\n")
    out.write_text("".join(lines), encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
