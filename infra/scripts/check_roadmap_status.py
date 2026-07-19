#!/usr/bin/env python3
"""Fail if roadmap MDX frontmatter status is not in the closed enum.

See web/content/roadmap/ROADMAP_CONVENTIONS.mdx.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

ALLOWED = frozenset({"completed", "planned", "in-progress", "superseded"})
STATUS_RE = re.compile(r'(?m)^status:\s*["\']?([^"\'\n]+)["\']?\s*$')


def frontmatter_status(text: str) -> str | None:
    if not text.startswith("---"):
        return None
    end = text.find("\n---", 3)
    if end < 0:
        return None
    block = text[3:end]
    m = STATUS_RE.search(block)
    if not m:
        return None
    return m.group(1).strip()


def main() -> int:
    root = Path(__file__).resolve().parents[2]
    roadmap = root / "web" / "content" / "roadmap"
    if not roadmap.is_dir():
        print(f"roadmap dir missing: {roadmap}", file=sys.stderr)
        return 1

    bad: list[str] = []
    checked = 0
    for path in sorted(roadmap.rglob("*.mdx")):
        status = frontmatter_status(path.read_text(encoding="utf-8"))
        if status is None:
            continue
        checked += 1
        if status not in ALLOWED:
            rel = path.relative_to(root)
            bad.append(f"{rel}: status={status!r} (allowed: {sorted(ALLOWED)})")

    if bad:
        print("check_roadmap_status: unknown status values:", file=sys.stderr)
        for line in bad:
            print(f"  {line}", file=sys.stderr)
        return 1

    print(f"check_roadmap_status: ok ({checked} files with status)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
