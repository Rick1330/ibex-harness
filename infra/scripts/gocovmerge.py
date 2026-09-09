#!/usr/bin/env python3
"""Merge Go cover profiles without pulling golang.org/x/tools (Go 1.26+).

Compatible with github.com/wadey/gocovmerge semantics for mode set/count/atomic.
"""

from __future__ import annotations

import sys
from dataclasses import dataclass
from pathlib import Path

# Cover block: statement count + hit count.
Block = tuple[int, int]
Blocks = dict[str, Block]


@dataclass(frozen=True, slots=True)
class _BlockHit:
    key: str
    stmts: int
    count: int


def _safe_path(raw: str, *, base: Path) -> Path:
    """Resolve argv paths and refuse escapes outside the working directory."""
    candidate = Path(raw)
    if candidate.is_absolute():
        resolved = candidate.resolve()
    else:
        resolved = (base / candidate).resolve()
    try:
        resolved.relative_to(base.resolve())
    except ValueError as exc:
        raise SystemExit(f"path escapes working directory: {raw}") from exc
    return resolved


def _parse_mode(header: str, path: Path) -> str:
    if not header.startswith("mode:"):
        raise SystemExit(f"bad cover profile (missing mode): {path}")
    return header.split(":", 1)[1].strip()


def _combine_counts(mode: str, prev: int, new: int) -> int:
    if mode == "set":
        return prev or new
    return prev + new


def _ingest_block(blocks: Blocks, mode: str, hit: _BlockHit) -> None:
    if hit.key not in blocks:
        blocks[hit.key] = (hit.stmts, hit.count)
        return
    prev_stmts, prev_count = blocks[hit.key]
    if prev_stmts != hit.stmts:
        raise SystemExit(f"statement count mismatch for {hit.key}")
    blocks[hit.key] = (hit.stmts, _combine_counts(mode, prev_count, hit.count))


def _ingest_profile_line(blocks: Blocks, mode: str, line: str) -> None:
    text = line.strip()
    if not text:
        return
    key, stmts_s, count_s = text.rsplit(" ", 2)
    _ingest_block(
        blocks,
        mode,
        _BlockHit(key=key, stmts=int(stmts_s), count=int(count_s)),
    )


def _read_profile(path: Path) -> tuple[str, list[str]]:
    lines = path.read_text(encoding="utf-8").splitlines()
    if not lines:
        raise SystemExit(f"bad cover profile (empty): {path}")
    return _parse_mode(lines[0], path), lines[1:]


def _apply_profile(blocks: Blocks, expected_mode: str | None, path: Path) -> str:
    file_mode, body = _read_profile(path)
    if expected_mode is None:
        mode = file_mode
    elif expected_mode != file_mode:
        raise SystemExit(f"mode mismatch: {expected_mode} vs {file_mode} ({path})")
    else:
        mode = expected_mode
    for line in body:
        _ingest_profile_line(blocks, mode, line)
    return mode


def _merge(paths: list[Path]) -> tuple[str, Blocks]:
    if not paths:
        raise SystemExit("no cover profiles provided")
    blocks: Blocks = {}
    mode = _apply_profile(blocks, None, paths[0])
    for path in paths[1:]:
        mode = _apply_profile(blocks, mode, path)
    return mode, blocks


def _write_profile(out: Path, mode: str, blocks: Blocks) -> None:
    lines = [f"mode: {mode}\n"]
    for key in sorted(blocks):
        stmts, count = blocks[key]
        lines.append(f"{key} {stmts} {count}\n")
    out.write_text("".join(lines), encoding="utf-8")


def main(argv: list[str]) -> int:
    if len(argv) < 3:
        print(
            f"usage: {argv[0]} <out.out> <profile1.out> [profile2.out ...]",
            file=sys.stderr,
        )
        return 2
    base = Path.cwd()
    out = _safe_path(argv[1], base=base)
    profiles = [_safe_path(p, base=base) for p in argv[2:]]
    for path in profiles:
        if not path.is_file():
            raise SystemExit(f"cover profile not found: {path}")
    mode, blocks = _merge(profiles)
    _write_profile(out, mode, blocks)
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
