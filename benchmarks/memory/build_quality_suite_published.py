#!/usr/bin/env python3
"""Merge ranking-quality or write-pipeline bench output into published history JSON."""

from __future__ import annotations

import argparse
import sys
from collections.abc import Callable
from pathlib import Path
from typing import Any

_BENCH_DIR = Path(__file__).resolve().parent
if str(_BENCH_DIR) not in sys.path:
    sys.path.insert(0, str(_BENCH_DIR))

from path_guard import (  # noqa: E402
    UnsafePathError,
    resolve_published_ranking_quality_path,
    resolve_published_write_pipeline_path,
)
from publish_quality_common import (  # noqa: E402
    RunMeta,
    load_json,
    merge_ranking_quality_entry,
    merge_run,
    merge_write_pipeline_entry,
)

SuiteConfig = tuple[str, Callable[[Path | str], Path], Callable[[dict[str, Any], dict[str, Any], RunMeta], dict[str, Any]]]

SUITES: dict[str, SuiteConfig] = {
    "ranking_quality": (
        "ranking_quality",
        resolve_published_ranking_quality_path,
        merge_ranking_quality_entry,
    ),
    "write_pipeline": (
        "write_pipeline",
        resolve_published_write_pipeline_path,
        merge_write_pipeline_entry,
    ),
}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--suite",
        required=True,
        choices=sorted(SUITES),
        help="Memory quality suite to publish",
    )
    parser.add_argument("--latest", type=Path, required=True)
    parser.add_argument("--gate", type=Path, required=True)
    parser.add_argument("--published", type=Path, required=True)
    parser.add_argument("--sha", required=True)
    parser.add_argument("--branch", default="main")
    parser.add_argument("--run-number", type=int, default=0)
    parser.add_argument("--run-url", default="")
    args = parser.parse_args()

    benchmark, resolve_published, merge_entry = SUITES[args.suite]
    try:
        published_path = resolve_published(args.published)
    except UnsafePathError as exc:
        parser.error(str(exc))

    latest = load_json(args.latest)
    gate = load_json(args.gate)
    entry = merge_entry(
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
        benchmark=benchmark,
        entry=entry,
        sha=args.sha,
    )
    print(f"wrote {published_path} status={entry['status']}", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
