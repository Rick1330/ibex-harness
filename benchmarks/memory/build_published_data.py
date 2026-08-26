"""Merge a raw HNSW bench result into the published history JSON."""

from __future__ import annotations

import argparse
import json
import sys
from datetime import UTC, datetime
from pathlib import Path

_BENCH_DIR = Path(__file__).resolve().parent
if str(_BENCH_DIR) not in sys.path:
    sys.path.insert(0, str(_BENCH_DIR))
from path_guard import UnsafePathError, resolve_workspace_path  # noqa: E402


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--raw", type=Path, required=True)
    parser.add_argument("--published", type=Path, required=True)
    parser.add_argument("--sha", required=True)
    parser.add_argument("--branch", default="main")
    parser.add_argument("--run-number", type=int, default=0)
    parser.add_argument("--run-url", default="")
    args = parser.parse_args()

    try:
        raw_path = resolve_workspace_path(args.raw, must_exist=True)
        published_path = resolve_workspace_path(args.published, allow_create_parent=True)
    except UnsafePathError as exc:
        parser.error(str(exc))

    raw = json.loads(raw_path.read_text(encoding="utf-8"))
    short = args.sha[:7] if len(args.sha) >= 7 else args.sha
    entry = {
        "sha": args.sha,
        "short_sha": short,
        "timestamp": raw.get("generated_at") or datetime.now(UTC).isoformat(),
        "branch": args.branch,
        "run_number": args.run_number,
        "run_url": args.run_url,
        "methodology": raw.get("methodology", {}),
        "results": raw.get("results", []),
        "mean_recall_at_10": raw.get("mean_recall_at_10", 0.0),
    }

    if published_path.exists():
        published = json.loads(published_path.read_text(encoding="utf-8"))
    else:
        published = {
            "schema_version": 1,
            "benchmark": "hnsw_recall_latency",
            "runs": [],
        }

    runs = [r for r in published.get("runs", []) if r.get("sha") != args.sha]
    runs.insert(0, entry)
    published["schema_version"] = 1
    published["benchmark"] = "hnsw_recall_latency"
    published["runs"] = runs[:50]

    published_path.parent.mkdir(parents=True, exist_ok=True)
    published_path.write_text(json.dumps(published, indent=2) + "\n", encoding="utf-8")
    print(f"wrote {published_path} ({len(runs)} runs)", flush=True)


if __name__ == "__main__":
    main()
