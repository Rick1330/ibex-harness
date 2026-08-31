#!/usr/bin/env python3
"""Fail CI when the latest published HNSW run has status != pass.

Reads the persisted `status` field written by build_published_data.py
(compute_status(compute_gate_summary(...))) — single source of truth.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path
from typing import Any


def _fail(message: str) -> None:
    print(f"check_hnsw_gate_status: {message}", file=sys.stderr)
    raise SystemExit(1)


def _load_published(path: Path) -> dict[str, Any]:
    if not path.is_file():
        _fail(f"published file not found: {path}")
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        _fail("published root must be an object")
    return payload


def _select_run(runs: list[Any], sha: str) -> dict[str, Any]:
    if not runs:
        _fail("published runs array is empty")
    if sha:
        for run in runs:
            if isinstance(run, dict) and run.get("sha") == sha:
                return run
        _fail(f"no published run found for sha {sha!r}")
    first = runs[0]
    if not isinstance(first, dict):
        _fail("run entry must be an object")
    return first


def _format_gate_summary(gate: dict[str, Any]) -> str:
    lines = ["HNSW gate_summary:"]
    for key in sorted(gate):
        lines.append(f"  {key}: {gate[key]}")
    return "\n".join(lines)


def _append_step_summary(text: str) -> None:
    summary_path = os.environ.get("GITHUB_STEP_SUMMARY")
    if not summary_path:
        return
    with open(summary_path, "a", encoding="utf-8") as fh:
        fh.write(text)
        if not text.endswith("\n"):
            fh.write("\n")


def check_gate_status(published_path: Path, *, sha: str = "") -> int:
    payload = _load_published(published_path)
    runs = payload.get("runs")
    if not isinstance(runs, list):
        _fail("published runs must be an array")

    run = _select_run(runs, sha)
    status = run.get("status")
    gate = run.get("gate_summary")
    if not isinstance(gate, dict):
        _fail("run gate_summary must be an object")

    run_sha = run.get("short_sha", run.get("sha", "?"))
    if status == "pass":
        print(f"ok: HNSW gate status=pass for run {run_sha}")
        return 0

    detail = _format_gate_summary(gate)
    message = (
        f"HNSW gate status={status!r} for run {run_sha} "
        f"(expected 'pass')\n{detail}"
    )
    print(message, file=sys.stderr)
    _append_step_summary(f"## HNSW gate enforcement failed\n\n```\n{detail}\n```\n")
    return 1


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--published",
        type=Path,
        required=True,
        help="Path to hnsw-benchmark-data.json",
    )
    parser.add_argument(
        "--sha",
        default=os.environ.get("GITHUB_SHA", ""),
        help="Commit SHA to match (default: GITHUB_SHA, else runs[0])",
    )
    args = parser.parse_args(argv)
    return check_gate_status(args.published.resolve(), sha=args.sha.strip())


if __name__ == "__main__":
    sys.exit(main())
