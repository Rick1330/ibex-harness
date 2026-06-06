#!/usr/bin/env python3
"""Extract FILE sections from monolith markdown sources into repo paths."""

from __future__ import annotations

import re
import sys
from pathlib import Path


def _unwrap_outer_fence(block: str) -> str:
    """Strip outer ``` or ```markdown fence; handles nested inner fences."""
    lines = block.strip().split("\n")
    if not lines:
        return block
    first = lines[0].strip()
    if not first.startswith("```"):
        return block
    for i in range(len(lines) - 1, 0, -1):
        if lines[i].strip() == "```":
            return "\n".join(lines[1:i])
    return block


def extract_sections(content: str, header_pattern: re.Pattern[str]) -> list[tuple[str, str]]:
    """Return list of (relative_path, body) from monolith content."""
    sections: list[tuple[str, str]] = []
    matches = list(header_pattern.finditer(content))
    for i, match in enumerate(matches):
        path = match.group(1).strip()
        start = match.end()
        end = matches[i + 1].start() if i + 1 < len(matches) else len(content)
        block = content[start:end].strip()
        # Strip leading --- separator lines
        block = re.sub(r"^---\s*\n", "", block)
        # Stop at PART B separator if present (roadmap monolith)
        part_b = re.search(
            r"^# ═+\s*\n# PART B\b",
            block,
            re.MULTILINE,
        )
        if part_b:
            block = block[: part_b.start()].rstrip()
        body = _unwrap_outer_fence(block)
        # Remove zero-width and other invisible chars that break fences
        body = body.replace("\u200b", "").replace("\ufeff", "")
        sections.append((path, body.rstrip() + "\n"))
    return sections


def main() -> int:
    if len(sys.argv) != 4:
        print("usage: extract_monolith_docs.py <source.md> <repo_root> <header_regex>")
        return 1

    source = Path(sys.argv[1])
    repo_root = Path(sys.argv[2])
    header_re = re.compile(sys.argv[3], re.MULTILINE)

    content = source.read_text(encoding="utf-8")
    sections = extract_sections(content, header_re)

    for rel_path, body in sections:
        out = repo_root / rel_path
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(body, encoding="utf-8", newline="\n")
        print(f"wrote {out.relative_to(repo_root)}")

    print(f"extracted {len(sections)} files")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
