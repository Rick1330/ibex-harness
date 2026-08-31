#!/usr/bin/env python3
"""Validate published write-pipeline-benchmark-data.json."""

from __future__ import annotations

import json
import sys
from pathlib import Path

try:
    import jsonschema
except ImportError:
    jsonschema = None  # type: ignore[assignment]

DATA_NAME = "write-pipeline-benchmark-data.json"
_SCHEMA_PATH = (
    Path(__file__).resolve().parents[1]
    / "data-schema"
    / "write-pipeline-benchmark-data.schema.json"
)


def fail(message: str) -> None:
    print(f"validate_published_write_pipeline: {message}", file=sys.stderr)
    raise SystemExit(1)


def resolve_path(raw: str) -> Path:
    if not raw or raw != raw.strip():
        fail("path must not be empty or whitespace")
    candidate = Path(raw)
    if candidate.is_absolute() or ".." in candidate.parts:
        fail("path must be workspace-relative without parent references")
    if candidate.name != DATA_NAME:
        fail(f"path must name {DATA_NAME}")
    resolved = (Path.cwd() / candidate).resolve()
    try:
        resolved.relative_to(Path.cwd().resolve())
    except ValueError:
        fail("path escapes workspace")
    if not resolved.is_file():
        fail(f"file not found: {candidate}")
    return resolved


def main(argv: list[str] | None = None) -> int:
    args = argv if argv is not None else sys.argv[1:]
    if len(args) != 1:
        fail("usage: validate_published_write_pipeline.py <path>")
    path = resolve_path(args[0])
    payload = json.loads(path.read_text(encoding="utf-8"))
    if jsonschema is None:
        print("jsonschema not installed; skipping schema validation", file=sys.stderr)
        return 0
    schema = json.loads(_SCHEMA_PATH.read_text(encoding="utf-8"))
    jsonschema.validate(payload, schema)
    print(f"ok: {path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
