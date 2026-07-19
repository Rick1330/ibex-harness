#!/usr/bin/env python3
"""Fail if roadmap MDX frontmatter status is not in the closed enum.

See web/content/roadmap/ROADMAP_CONVENTIONS.mdx.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

ALLOWED = frozenset({"completed", "planned", "in-progress", "superseded"})
STATUS_RE = re.compile(r'(?m)^status:\s*["\']?([\w-]+)["\']?\s*$')


def frontmatter_block(text: str) -> str | None:
    if not text.startswith("---"):
        return None
    end = text.find("\n---", 3)
    if end < 0:
        return None
    return text[3:end]


def frontmatter_status(text: str) -> str | None:
    block = frontmatter_block(text)
    if block is None:
        return None
    match = STATUS_RE.search(block)
    if match is None:
        return None
    return match.group(1).strip()


def collect_bad_statuses(roadmap: Path, root: Path) -> list[str]:
    bad: list[str] = []
    for path in sorted(roadmap.rglob("*.mdx")):
        status = frontmatter_status(path.read_text(encoding="utf-8"))
        if status is None:
            continue
        if status in ALLOWED:
            continue
        rel = path.relative_to(root)
        bad.append(f"{rel}: status={status!r} (allowed: {sorted(ALLOWED)})")
    return bad


def count_status_files(roadmap: Path) -> int:
    checked = 0
    for path in roadmap.rglob("*.mdx"):
        if frontmatter_status(path.read_text(encoding="utf-8")) is not None:
            checked += 1
    return checked


def main() -> int:
    root = Path(__file__).resolve().parents[2]
    roadmap = root / "web" / "content" / "roadmap"
    if not roadmap.is_dir():
        print(f"roadmap dir missing: {roadmap}", file=sys.stderr)
        return 1

    bad = collect_bad_statuses(roadmap, root)
    if bad:
        print("check_roadmap_status: unknown status values:", file=sys.stderr)
        for line in bad:
            print(f"  {line}", file=sys.stderr)
        return 1

    checked = count_status_files(roadmap)
    print(f"check_roadmap_status: ok ({checked} files with status)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
