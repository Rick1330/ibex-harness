"""Merge a raw HNSW bench result into the published history JSON."""

from __future__ import annotations

import argparse
import json
from datetime import UTC, datetime
from pathlib import Path


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--raw", type=Path, required=True)
    parser.add_argument("--published", type=Path, required=True)
    parser.add_argument("--sha", required=True)
    parser.add_argument("--branch", default="main")
    parser.add_argument("--run-number", type=int, default=0)
    parser.add_argument("--run-url", default="")
    args = parser.parse_args()

    raw = json.loads(args.raw.read_text(encoding="utf-8"))
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

    if args.published.exists():
        published = json.loads(args.published.read_text(encoding="utf-8"))
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

    args.published.parent.mkdir(parents=True, exist_ok=True)
    args.published.write_text(json.dumps(published, indent=2) + "\n", encoding="utf-8")
    print(f"wrote {args.published} ({len(runs)} runs)", flush=True)


if __name__ == "__main__":
    main()
