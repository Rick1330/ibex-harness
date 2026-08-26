"""Merge a raw HNSW bench result into the published history JSON.

Published cells are production knobs only:
  ef_search=40, min_similarity≈0.70, iterative_scan=off, index_build_mode=bulk
Full matrix remains in the raw artifact under benchmarks/memory/output/.
"""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

_BENCH_DIR = Path(__file__).resolve().parent
if str(_BENCH_DIR) not in sys.path:
    sys.path.insert(0, str(_BENCH_DIR))
from path_guard import (  # noqa: E402
    UnsafePathError,
    resolve_published_hnsw_path,
    resolve_raw_bench_path,
)

_PUBLISH_EF_SEARCH = 40
_PUBLISH_MIN_SIMILARITY = 0.70
_PUBLISH_MIN_SIM_TOLERANCE = 0.001
_PUBLISH_ITERATIVE_SCAN = "off"
_PUBLISH_INDEX_BUILD_MODE = "bulk"
_RECALL_SLA = 0.98
_P95_SLA_MS_1M = 30.0
_P99_SLA_MS_1M = 100.0


@dataclass(frozen=True, slots=True)
class RunMeta:
    sha: str
    branch: str
    run_number: int
    run_url: str


def _is_production_cell(result: dict[str, Any]) -> bool:
    ef = result.get("ef_search")
    if ef != _PUBLISH_EF_SEARCH:
        return False
    min_sim = result.get("min_similarity")
    if min_sim is None:
        return False
    try:
        if abs(float(min_sim) - _PUBLISH_MIN_SIMILARITY) > _PUBLISH_MIN_SIM_TOLERANCE:
            return False
    except (TypeError, ValueError):
        return False
    if result.get("iterative_scan", _PUBLISH_ITERATIVE_SCAN) != _PUBLISH_ITERATIVE_SCAN:
        return False
    if result.get("index_build_mode", _PUBLISH_INDEX_BUILD_MODE) != _PUBLISH_INDEX_BUILD_MODE:
        return False
    return True


def filter_published_results(results: list[Any]) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for item in results:
        if isinstance(item, dict) and _is_production_cell(item):
            out.append(item)
    return out


def compute_gate_summary(results: list[dict[str, Any]]) -> dict[str, Any]:
    if not results:
        return {
            "recall_ok": False,
            "recall_floor": _RECALL_SLA,
            "worst_recall_at_10": 0.0,
            "has_1m": False,
            "note": "no production cells after filter",
        }
    recalls = [float(r["recall_at_10"]) for r in results]
    worst = min(recalls)
    recall_ok = worst >= _RECALL_SLA
    at_1m = next((r for r in results if int(r["corpus_size"]) >= 1_000_000), None)
    summary: dict[str, Any] = {
        "recall_ok": recall_ok,
        "recall_floor": _RECALL_SLA,
        "worst_recall_at_10": worst,
        "has_1m": at_1m is not None,
    }
    if at_1m is not None:
        p95 = float(at_1m["latency_ms_p95"])
        p99 = float(at_1m["latency_ms_p99"])
        summary["p95_ms_1m"] = p95
        summary["p99_ms_1m"] = p99
        summary["p95_1m_ok"] = p95 < _P95_SLA_MS_1M
        summary["p99_1m_ok"] = p99 < _P99_SLA_MS_1M
    else:
        summary["note"] = "1M cell absent (expected on smoke/fast profiles)"
    return summary


def compute_status(gate: dict[str, Any]) -> str:
    if not gate.get("recall_ok", False):
        return "fail"
    if gate.get("has_1m"):
        if not gate.get("p95_1m_ok", True) or not gate.get("p99_1m_ok", True):
            return "fail"
        return "pass"
    return "warn"


def _merge_entry(raw: dict, meta: RunMeta) -> dict:
    short = meta.sha[:7] if len(meta.sha) >= 7 else meta.sha
    filtered = filter_published_results(list(raw.get("results") or []))
    if not filtered:
        msg = (
            "no production HNSW cells to publish "
            f"(need ef_search={_PUBLISH_EF_SEARCH}, "
            f"min_similarity≈{_PUBLISH_MIN_SIMILARITY}, "
            f"iterative_scan={_PUBLISH_ITERATIVE_SCAN}, "
            f"index_build_mode={_PUBLISH_INDEX_BUILD_MODE})"
        )
        raise RuntimeError(msg)
    mean = sum(float(r["recall_at_10"]) for r in filtered) / len(filtered)
    gate = compute_gate_summary(filtered)
    methodology = dict(raw.get("methodology") or {})
    methodology["note"] = (
        "Published cells: ef_search=40, min_similarity=0.70, "
        "iterative_scan=off, bulk index build. Full matrix retained under "
        "benchmarks/memory/output/."
    )
    methodology["min_similarity_values"] = [_PUBLISH_MIN_SIMILARITY]
    methodology["iterative_scan_modes"] = [_PUBLISH_ITERATIVE_SCAN]
    methodology["index_build_modes"] = [_PUBLISH_INDEX_BUILD_MODE]
    return {
        "sha": meta.sha,
        "short_sha": short,
        "timestamp": raw.get("generated_at") or datetime.now(UTC).isoformat(),
        "branch": meta.branch,
        "run_number": meta.run_number,
        "run_url": meta.run_url,
        "methodology": methodology,
        "results": filtered,
        "mean_recall_at_10": mean,
        "status": compute_status(gate),
        "gate_summary": gate,
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
        RunMeta(
            sha=args.sha,
            branch=args.branch,
            run_number=args.run_number,
            run_url=args.run_url,
        ),
    )
    published = _load_or_init_published(published_path)
    runs = [r for r in published.get("runs", []) if r.get("sha") != args.sha]
    runs.insert(0, entry)
    published["schema_version"] = 1
    published["benchmark"] = "hnsw_recall_latency"
    published["runs"] = runs[:50]
    _write_published(published_path, published)
    print(f"wrote {published_path} ({len(runs)} runs) status={entry['status']}", flush=True)


if __name__ == "__main__":
    main()
