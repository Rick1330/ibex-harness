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
from path_guard import (  # noqa: E402
    UnsafePathError,
    resolve_published_hnsw_path,
    resolve_raw_bench_path,
)


def _merge_entry(raw: dict, *, sha: str, branch: str, run_number: int, run_url: str) -> dict:
    short = sha[:7] if len(sha) >= 7 else sha
    return {
        "sha": sha,
        "short_sha": short,
        "timestamp": raw.get("generated_at") or datetime.now(UTC).isoformat(),
        "branch": branch,
        "run_number": run_number,
        "run_url": run_url,
        "methodology": raw.get("methodology", {}),
        "results": raw.get("results", []),
        "mean_recall_at_10": raw.get("mean_recall_at_10", 0.0),
    }


def _load_or_init_published(published_path: Path) -> dict:
    if not published_path.exists():
        return {
            "schema_version": 1,
            "benchmark": "hnsw_recall_latency",
            "runs": [],
        }
    return json.loads(published_path.read_text(encoding="utf-8"))


def _write_published(published_path: Path, published: dict) -> None:
    published_path.parent.mkdir(parents=True, exist_ok=True)
    # Path already basename-allowlisted + workspace-bound in path_guard.
    published_path.write_text(  # NOSONAR pythonsecurity:S2083,pythonsecurity:S8707
        json.dumps(published, indent=2) + "\n",
        encoding="utf-8",
    )


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
        raw_path = resolve_raw_bench_path(args.raw, must_exist=True)
        published_path = resolve_published_hnsw_path(args.published)
    except UnsafePathError as exc:
        parser.error(str(exc))

    raw = json.loads(raw_path.read_text(encoding="utf-8"))  # NOSONAR pythonsecurity:S2083
    entry = _merge_entry(
        raw,
        sha=args.sha,
        branch=args.branch,
        run_number=args.run_number,
        run_url=args.run_url,
    )
    published = _load_or_init_published(published_path)
    runs = [r for r in published.get("runs", []) if r.get("sha") != args.sha]
    runs.insert(0, entry)
    published["schema_version"] = 1
    published["benchmark"] = "hnsw_recall_latency"
    published["runs"] = runs[:50]
    _write_published(published_path, published)
    print(f"wrote {published_path} ({len(runs)} runs)", flush=True)


if __name__ == "__main__":
    main()
