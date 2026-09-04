#!/usr/bin/env python3
"""Merge extraction-quality eval output into published history JSON."""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from path_guard import (
    PUBLISHED_NAME,
    UnsafePathError,
    resolve_gate_input_path,
    resolve_latest_path,
    resolve_published_extraction_path,
)

MAX_RUNS = 50


@dataclass(frozen=True, slots=True)
class RunMeta:
    sha: str
    branch: str
    run_number: int
    run_url: str


def load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))  # NOSONAR pythonsecurity:S2083


def build_entry(
    latest: dict[str, Any],
    gate: dict[str, Any],
    meta: RunMeta,
) -> dict[str, Any]:
    metrics = latest.get("metrics") or {}
    return {
        "sha": meta.sha,
        "short_sha": meta.sha[:7],
        "timestamp": datetime.now(UTC).isoformat(),
        "branch": meta.branch,
        "run_number": meta.run_number,
        "run_url": meta.run_url,
        "gold_set": latest.get("gold_set", "v1"),
        "conversation_count": int(latest.get("conversation_count") or 0),
        "provider": latest.get("provider", "openai"),
        "enforcement": latest.get("enforcement", "ci"),
        "mode": latest.get("mode", "cassette"),
        "model": latest.get("model"),
        "metrics": {
            "precision_macro": float(metrics.get("precision_macro", 0.0)),
            "recall_macro": float(metrics.get("recall_macro", 0.0)),
            "category_assignment_accuracy": float(
                metrics.get("category_assignment_accuracy", 0.0)
            ),
            "temporal_field_accuracy": float(metrics.get("temporal_field_accuracy", 0.0)),
            "precision_factual": float(metrics.get("precision_factual", 0.0)),
            "recall_factual": float(metrics.get("recall_factual", 0.0)),
            "precision_preference": float(metrics.get("precision_preference", 0.0)),
            "recall_preference": float(metrics.get("recall_preference", 0.0)),
            "precision_behavioral": float(metrics.get("precision_behavioral", 0.0)),
            "recall_behavioral": float(metrics.get("recall_behavioral", 0.0)),
            "precision_episodic": float(metrics.get("precision_episodic", 0.0)),
            "recall_episodic": float(metrics.get("recall_episodic", 0.0)),
            "precision_procedural": float(metrics.get("precision_procedural", 0.0)),
            "recall_procedural": float(metrics.get("recall_procedural", 0.0)),
        },
        "status": "pass" if gate.get("status") == "pass" else "fail",
        "gate_summary": {
            "status": gate.get("status"),
            "checks": gate.get("checks") or [],
        },
    }


def _run_timestamp(run: dict[str, Any]) -> str:
    return str(run.get("timestamp") or "")


def merge_run(published_path: Path, entry: dict[str, Any], sha: str) -> None:
    if published_path.exists():
        data = load_json(published_path)
    else:
        data = {"schema_version": 1, "benchmark": "extraction_quality", "runs": []}
    if data.get("benchmark") != "extraction_quality":
        raise SystemExit("published file benchmark must be extraction_quality")
    runs = list(data.get("runs") or [])
    runs = [r for r in runs if str(r.get("sha", "")).lower() != sha.lower()]
    runs.append(entry)
    runs.sort(key=_run_timestamp, reverse=True)
    data["runs"] = runs[:MAX_RUNS]
    data["schema_version"] = 1
    data["benchmark"] = "extraction_quality"
    published_path.parent.mkdir(parents=True, exist_ok=True)
    published_path.write_text(  # NOSONAR pythonsecurity:S2083,pythonsecurity:S8707
        json.dumps(data, indent=2) + "\n",
        encoding="utf-8",
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--latest", type=Path, required=True)
    parser.add_argument("--gate", type=Path, required=True)
    parser.add_argument("--published", type=Path, required=True)
    parser.add_argument("--sha", required=True)
    parser.add_argument("--branch", default="main")
    parser.add_argument("--run-number", type=int, default=0)
    parser.add_argument("--run-url", default="")
    args = parser.parse_args(argv)

    try:
        latest_path = resolve_latest_path(args.latest)
        gate_path = resolve_gate_input_path(args.gate)
        published = resolve_published_extraction_path(args.published)
    except UnsafePathError as exc:
        print(str(exc), file=sys.stderr)
        return 1

    if published.name != PUBLISHED_NAME:
        print(f"published path must be named {PUBLISHED_NAME}", file=sys.stderr)
        return 1

    latest = load_json(latest_path)
    gate = load_json(gate_path)
    entry = build_entry(
        latest,
        gate,
        RunMeta(
            sha=args.sha,
            branch=args.branch,
            run_number=args.run_number,
            run_url=args.run_url,
        ),
    )
    merge_run(published, entry, args.sha)
    print(f"wrote {published} status={entry['status']}", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
