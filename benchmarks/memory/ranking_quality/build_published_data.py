#!/usr/bin/env python3
"""Merge ranking-quality bench output into published history JSON."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

_BENCH_DIR = Path(__file__).resolve().parents[1]
if str(_BENCH_DIR) not in sys.path:
    sys.path.insert(0, str(_BENCH_DIR))

from path_guard import UnsafePathError, resolve_published_ranking_quality_path  # noqa: E402
from publish_quality_common import (  # noqa: E402
    RunMeta,
    gate_status,
    load_json,
    merge_run,
    run_entry_base,
)

_BENCHMARK = "ranking_quality"


def _merge_entry(latest: dict, gate: dict, meta: RunMeta) -> dict:
    return {
        **run_entry_base(meta, timestamp=str(latest.get("timestamp") or None)),
        "gold_set": latest.get("gold_set", "v1"),
        "query_count": latest.get("query_count", 0),
        "memory_count": latest.get("memory_count", 0),
        "metrics": dict(latest.get("metrics") or {}),
        "status": gate_status(gate),
        "gate_summary": gate,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--latest", type=Path, required=True)
    parser.add_argument("--gate", type=Path, required=True)
    parser.add_argument("--published", type=Path, required=True)
    parser.add_argument("--sha", required=True)
    parser.add_argument("--branch", default="main")
    parser.add_argument("--run-number", type=int, default=0)
    parser.add_argument("--run-url", default="")
    args = parser.parse_args()

    try:
        published_path = resolve_published_ranking_quality_path(args.published)
    except UnsafePathError as exc:
        parser.error(str(exc))

    latest = load_json(args.latest)
    gate = load_json(args.gate)
    entry = _merge_entry(
        latest,
        gate,
        RunMeta(
            sha=args.sha,
            branch=args.branch,
            run_number=args.run_number,
            run_url=args.run_url,
        ),
    )
    merge_run(
        published_path,
        benchmark=_BENCHMARK,
        entry=entry,
        sha=args.sha,
    )
    print(f"wrote {published_path} status={entry['status']}", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
