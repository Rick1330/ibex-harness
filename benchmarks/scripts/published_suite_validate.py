"""Shared helpers for published memory-suite benchmark JSON validators."""

from __future__ import annotations

import json
import sys
from pathlib import Path

try:
    import jsonschema
except ImportError:
    jsonschema = None  # type: ignore[assignment]


def fail(script_name: str, message: str) -> None:
    print(f"{script_name}: {message}", file=sys.stderr)
    raise SystemExit(1)


def resolve_published_data_path(raw: str, *, data_name: str, script_name: str) -> Path:
    if not raw or raw != raw.strip():
        fail(script_name, "path must not be empty or whitespace")
    candidate = Path(raw)
    if candidate.is_absolute() or ".." in candidate.parts:
        fail(script_name, "path must be workspace-relative without parent references")
    if candidate.name != data_name:
        fail(script_name, f"path must name {data_name}")
    resolved = (Path.cwd() / candidate).resolve()
    try:
        resolved.relative_to(Path.cwd().resolve())
    except ValueError:
        fail(script_name, "path escapes workspace")
    if not resolved.is_file():
        fail(script_name, f"file not found: {candidate}")
    return resolved


def validate_published_payload(path: Path, schema_path: Path, *, script_name: str) -> None:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if jsonschema is None:
        print(f"{script_name}: jsonschema not installed; skipping schema validation", file=sys.stderr)
        return
    schema = json.loads(schema_path.read_text(encoding="utf-8"))
    jsonschema.validate(payload, schema)
    print(f"ok: {path}")
