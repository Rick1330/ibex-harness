#!/usr/bin/env python3
"""Validate published benchmark-data.json against schema and sanity bounds."""
from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

MAX_RUNS = 365
MAX_P99_MS = 500.0
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


def validate_k6(k6: Any, label: str) -> None:
    data = require_dict(k6, label)
    p99 = require_number(data.get("p99_ms"), f"{label}.p99_ms")
    if p99 <= 0 or p99 > MAX_P99_MS:
        fail(f"{label}.p99_ms out of bounds: {p99}")
    error_rate = require_number(data.get("error_rate"), f"{label}.error_rate")
    if error_rate < 0 or error_rate > 1:
        fail(f"{label}.error_rate out of bounds: {error_rate}")


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
    validate_k6(data.get("k6"), f"{label}.k6")


def validate_payload(payload: Any) -> None:
    data = require_dict(payload, "root")
    if data.get("schema_version") != 1:
        fail("schema_version must be 1")
    require_string(data.get("baseline_sha"), "baseline_sha")
    runs = data.get("runs")
    if not isinstance(runs, list):
        fail("runs must be an array")
    if len(runs) > MAX_RUNS:
        fail(f"runs exceeds max {MAX_RUNS}")
    seen_sha: set[str] = set()
    seen_pr: set[int] = set()
    for index, run in enumerate(runs):
        validate_run(run, index)
        run_data = require_dict(run, f"runs[{index}]")
        sha = require_string(run_data.get("sha"), f"runs[{index}].sha")
        if sha in seen_sha:
            fail(f"duplicate sha: {sha}")
        seen_sha.add(sha)
        pr_number = run_data.get("pr_number")
        if isinstance(pr_number, int):
            if pr_number in seen_pr:
                fail(f"duplicate pr_number: {pr_number}")
            seen_pr.add(pr_number)


def main() -> int:
    if len(sys.argv) != 2:
        fail("usage: validate_published_data.py <path-to-benchmark-data.json>")
    path = Path(sys.argv[1])
    if not path.exists():
        fail(f"file not found: {path}")
    payload = json.loads(path.read_text(encoding="utf-8"))
    validate_payload(payload)
    print(json.dumps({"ok": True, "runs": len(payload.get("runs", []))}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
