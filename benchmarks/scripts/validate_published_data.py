#!/usr/bin/env python3
"""Validate published benchmark-data.json against schema and sanity bounds."""
from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

MAX_RUNS = 365
MAX_P99_MS = 500.0
MAX_RUN_NUMBER = 1_000_000
BENCHMARK_DATA_NAME = "benchmark-data.json"
VALID_STATUSES = frozenset({"pass", "regression", "fail", "unknown"})


def fail(message: str) -> None:
    print(f"validate_published_data: {message}", file=sys.stderr)
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


def resolve_benchmark_data_path(raw: str) -> Path:
    if not raw or raw != raw.strip():
        fail("path must not be empty or whitespace")
    candidate = Path(raw)
    if candidate.is_absolute():
        fail("absolute paths are not allowed")
    if ".." in candidate.parts:
        fail("path must not contain parent references")
    if candidate.name != BENCHMARK_DATA_NAME:
        fail(f"path must name {BENCHMARK_DATA_NAME}")
    workspace = Path.cwd().resolve()
    resolved = (workspace / candidate).resolve()
    try:
        resolved.relative_to(workspace)
    except ValueError:
        fail("path escapes workspace")
    if not resolved.is_file():
        fail(f"file not found: {candidate}")
    return resolved


def validate_k6(k6: Any, label: str) -> None:
    data = require_dict(k6, label)
    p99 = require_number(data.get("p99_ms"), f"{label}.p99_ms")
    if p99 <= 0 or p99 > MAX_P99_MS:
        fail(f"{label}.p99_ms out of bounds: {p99}")
    error_rate = require_number(data.get("error_rate"), f"{label}.error_rate")
    if error_rate < 0 or error_rate > 1:
        fail(f"{label}.error_rate out of bounds: {error_rate}")


def require_run_number_int(value: Any, label: str) -> int:
    if not isinstance(value, int) or isinstance(value, bool):
        fail(f"{label}.run_number must be an integer")
    if value <= 0 or value > MAX_RUN_NUMBER:
        fail(f"{label}.run_number out of bounds: {value}")
    return value


def run_id_from_actions_url(run_url: Any) -> int | None:
    if not isinstance(run_url, str):
        return None
    marker = "/actions/runs/"
    if marker not in run_url:
        return None
    run_id_text = run_url.rsplit(marker, maxsplit=1)[-1].strip("/")
    if not run_id_text.isdigit():
        return None
    return int(run_id_text)


def validate_run_number(run_data: dict[str, Any], label: str) -> None:
    run_number_value = run_data.get("run_number")
    if run_number_value is None:
        return
    run_number = require_run_number_int(run_number_value, label)
    run_id = run_id_from_actions_url(run_data.get("run_url"))
    if run_id is not None and run_number == run_id:
        fail(f"{label}.run_number must be the workflow run number, not the run id")


def validate_run(run: Any, index: int) -> None:
    label = f"runs[{index}]"
    data = require_dict(run, label)
    require_string(data.get("sha"), f"{label}.sha")
    require_string(data.get("short_sha"), f"{label}.short_sha")
    status = require_string(data.get("status"), f"{label}.status")
    if status not in VALID_STATUSES:
        fail(f"{label}.status invalid: {status}")
    pr_number = data.get("pr_number")
    if pr_number is not None and not isinstance(pr_number, int):
        fail(f"{label}.pr_number must be an integer or null")
    validate_run_number(data, label)
    validate_k6(data.get("k6"), f"{label}.k6")


def track_run_identity(
    run_data: dict[str, Any],
    index: int,
    seen_sha: set[str],
    seen_pr: set[int],
) -> None:
    sha = require_string(run_data.get("sha"), f"runs[{index}].sha")
    if sha in seen_sha:
        fail(f"duplicate sha: {sha}")
    seen_sha.add(sha)
    pr_number = run_data.get("pr_number")
    if not isinstance(pr_number, int):
        return
    if pr_number in seen_pr:
        fail(f"duplicate pr_number: {pr_number}")
    seen_pr.add(pr_number)


def validate_runs_list(runs: Any) -> None:
    if not isinstance(runs, list):
        fail("runs must be an array")
    if len(runs) > MAX_RUNS:
        fail(f"runs exceeds max {MAX_RUNS}")
    seen_sha: set[str] = set()
    seen_pr: set[int] = set()
    for index, run in enumerate(runs):
        validate_run(run, index)
        run_data = require_dict(run, f"runs[{index}]")
        track_run_identity(run_data, index, seen_sha, seen_pr)


def validate_payload(payload: Any) -> None:
    data = require_dict(payload, "root")
    if data.get("schema_version") != 1:
        fail("schema_version must be 1")
    require_string(data.get("baseline_sha"), "baseline_sha")
    validate_runs_list(data.get("runs"))


def load_payload(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        fail("benchmark data root must be an object")
    return payload


def main() -> int:
    if len(sys.argv) != 2:
        fail("usage: validate_published_data.py <path-to-benchmark-data.json>")
    path = resolve_benchmark_data_path(sys.argv[1])
    payload = load_payload(path)
    validate_payload(payload)
    runs = payload.get("runs", [])
    run_count = len(runs) if isinstance(runs, list) else 0
    print(json.dumps({"ok": True, "runs": run_count}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
