#!/usr/bin/env python3
"""Validate published hnsw-benchmark-data.json against schema + sanity bounds."""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path
from typing import Any

MAX_RUNS = 50
HNSW_DATA_NAME = "hnsw-benchmark-data.json"
VALID_STATUSES = frozenset({"pass", "fail", "warn"})
_SHA_RE = re.compile(r"^[0-9a-f]{7,40}$", re.IGNORECASE)
_SCHEMA_PATH = (
    Path(__file__).resolve().parents[1] / "data-schema" / "hnsw-benchmark-data.schema.json"
)


def fail(message: str) -> None:
    print(f"validate_published_hnsw: {message}", file=sys.stderr)
    raise SystemExit(1)


def require_dict(value: Any, label: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        fail(f"{label} must be an object")
    return value


def require_number(value: Any, label: str) -> float:
    if not isinstance(value, (int, float)) or isinstance(value, bool):
        fail(f"{label} must be a number")
    return float(value)


def require_string(value: Any, label: str) -> str:
    if not isinstance(value, str):
        fail(f"{label} must be a string")
    return value


def require_sha_ref(value: Any, label: str) -> str:
    text = require_string(value, label)
    if not text or not _SHA_RE.match(text):
        fail(f"{label} must be hexadecimal sha")
    return text.lower()


def resolve_hnsw_data_path(raw: str) -> Path:
    if not raw or raw != raw.strip():
        fail("path must not be empty or whitespace")
    candidate = Path(raw)
    if candidate.is_absolute():
        fail("absolute paths are not allowed")
    if ".." in candidate.parts:
        fail("path must not contain parent references")
    if candidate.name != HNSW_DATA_NAME:
        fail(f"path must name {HNSW_DATA_NAME}")
    workspace = Path.cwd().resolve()
    resolved = (workspace / candidate).resolve()
    try:
        resolved.relative_to(workspace)
    except ValueError:
        fail("path escapes workspace")
    if not resolved.is_file():
        fail(f"file not found: {candidate}")
    return resolved


def require_nonneg_int(value: Any, label: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        fail(f"{label} must be a non-negative int")
    if value < 0:
        fail(f"{label} must be a non-negative int")
    return value


def require_unit_interval(value: Any, label: str) -> float:
    number = require_number(value, label)
    if number < 0 or number > 1:
        fail(f"{label} out of range")
    return number


def validate_result(result: Any, label: str) -> None:
    data = require_dict(result, label)
    require_number(data.get("corpus_size"), f"{label}.corpus_size")
    require_number(data.get("query_count"), f"{label}.query_count")
    require_unit_interval(data.get("recall_at_10"), f"{label}.recall_at_10")
    for key in ("latency_ms_p50", "latency_ms_p95", "latency_ms_p99"):
        val = require_number(data.get(key), f"{label}.{key}")
        if val < 0:
            fail(f"{label}.{key} must be non-negative")
    ef = require_number(data.get("ef_search"), f"{label}.ef_search")
    if ef < 1:
        fail(f"{label}.ef_search must be >= 1")


def validate_run_meta(data: dict[str, Any], label: str) -> None:
    require_sha_ref(data.get("sha"), f"{label}.sha")
    require_sha_ref(data.get("short_sha"), f"{label}.short_sha")
    require_string(data.get("timestamp"), f"{label}.timestamp")
    require_string(data.get("branch"), f"{label}.branch")
    require_nonneg_int(data.get("run_number"), f"{label}.run_number")
    require_string(data.get("run_url"), f"{label}.run_url")
    require_dict(data.get("methodology"), f"{label}.methodology")
    require_unit_interval(data.get("mean_recall_at_10"), f"{label}.mean_recall_at_10")
    status = data.get("status")
    if status is not None and status not in VALID_STATUSES:
        fail(f"{label}.status invalid")


def validate_run_results(data: dict[str, Any], label: str) -> None:
    results = data.get("results")
    if not isinstance(results, list) or not results:
        fail(f"{label}.results must be a non-empty array")
    for ri, result in enumerate(results):
        validate_result(result, f"{label}.results[{ri}]")


def validate_run(run: Any, index: int) -> None:
    label = f"runs[{index}]"
    data = require_dict(run, label)
    validate_run_meta(data, label)
    validate_run_results(data, label)


def validate_schema_identity(payload: dict[str, Any]) -> None:
    if payload.get("schema_version") != 1:
        fail("schema_version must be 1")
    if payload.get("benchmark") != "hnsw_recall_latency":
        fail("benchmark must be hnsw_recall_latency")


def validate_runs_list(runs: Any) -> None:
    if not isinstance(runs, list):
        fail("runs must be an array")
    if len(runs) > MAX_RUNS:
        fail(f"runs exceeds max {MAX_RUNS}")
    for index, run in enumerate(runs):
        validate_run(run, index)


def validate_payload(payload: dict[str, Any]) -> None:
    validate_schema_identity(payload)
    validate_runs_list(payload.get("runs"))


def validate_against_json_schema(payload: dict[str, Any], *, strict: bool = False) -> None:
    try:
        import jsonschema  # type: ignore[import-untyped]
    except ImportError:
        if strict:
            fail("jsonschema is required in strict mode")
        print("validate_published_hnsw: jsonschema not installed; skipping Draft schema check")
        return
    if not _SCHEMA_PATH.is_file():
        fail(f"schema missing: {_SCHEMA_PATH}")
    schema = json.loads(_SCHEMA_PATH.read_text(encoding="utf-8"))
    try:
        jsonschema.validate(instance=payload, schema=schema)
    except jsonschema.ValidationError as exc:  # type: ignore[attr-defined]
        fail(f"jsonschema: {exc.message}")


def parse_args(argv: list[str]) -> tuple[str, bool]:
    strict = False
    path: str | None = None
    for arg in argv:
        if arg == "--strict":
            strict = True
            continue
        if path is not None:
            fail("usage: validate_published_hnsw.py [--strict] <path-to-hnsw-benchmark-data.json>")
        path = arg
    if path is None:
        fail("usage: validate_published_hnsw.py [--strict] <path-to-hnsw-benchmark-data.json>")
    return path, strict


def main(argv: list[str] | None = None) -> None:
    args = argv if argv is not None else sys.argv[1:]
    raw_path, strict = parse_args(args)
    path = resolve_hnsw_data_path(raw_path)
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        fail("root must be an object")
    validate_payload(payload)
    validate_against_json_schema(payload, strict=strict)
    print(f"ok: {path} ({len(payload.get('runs', []))} runs)")


if __name__ == "__main__":
    main()
