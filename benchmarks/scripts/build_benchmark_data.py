#!/usr/bin/env python3
from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

OUT_DIR = Path("benchmarks/output")
BASELINE_PATH = Path("benchmarks/data-schema/baseline.json")
PREV_PATH = OUT_DIR / "prev-benchmark-data.json"
LATEST_PATH = OUT_DIR / "latest.json"
GATE_RESULT_PATH = OUT_DIR / "gate-result.json"
OUTPUT_PATH = OUT_DIR / "benchmark-data.json"
MAX_RUNS = 365


def synthetic_us_to_ms(value: float) -> float:
    return value / 1000.0


def map_stages(stage: dict[str, Any]) -> dict[str, float]:
    auth_us = float(stage.get("synthetic_auth_us", 0.0))
    return {
        "auth_lru_p99_ms": synthetic_us_to_ms(auth_us * 0.7),
        "auth_grpc_p99_ms": synthetic_us_to_ms(auth_us * 0.3),
        "rate_limit_p99_ms": synthetic_us_to_ms(float(stage.get("synthetic_rate_limit_us", 0.0))),
        "directive_resolve_p99_ms": synthetic_us_to_ms(float(stage.get("synthetic_directive_us", 0.0))),
        "prompt_inject_p99_ms": synthetic_us_to_ms(float(stage.get("synthetic_prompt_us", 0.0))),
        "total_overhead_p99_ms": synthetic_us_to_ms(float(stage.get("synthetic_total_us", 0.0))),
    }


def map_k6(k6_raw: dict[str, Any], k6_summary_path: Path) -> dict[str, Any]:
    vus = 100
    duration_s = 120.0
    if k6_summary_path.exists():
        summary = json.loads(k6_summary_path.read_text(encoding="utf-8"))
        duration_ms = summary.get("state", {}).get("testRunDurationMs")
        if duration_ms:
            duration_s = float(duration_ms) / 1000.0
    return {
        "vus": vus,
        "duration_s": duration_s,
        "p50_ms": float(k6_raw.get("p50_ms", 0.0)),
        "p95_ms": float(k6_raw.get("p95_ms", 0.0)),
        "p99_ms": float(k6_raw.get("p99_ms", 0.0)),
        "p999_ms": float(k6_raw.get("p999_ms", 0.0)),
        "req_per_s": float(k6_raw.get("req_per_s", 0.0)),
        "error_rate": float(k6_raw.get("error_rate", 0.0)),
        "check_rate": float(k6_raw.get("check_rate", 0.0)),
    }


def load_gate_result() -> dict[str, Any]:
    if not GATE_RESULT_PATH.exists():
        return {"status": "unknown", "regression_pct": None}
    return json.loads(GATE_RESULT_PATH.read_text(encoding="utf-8"))


def load_baseline_sha() -> str:
    if not BASELINE_PATH.exists():
        return ""
    baseline = json.loads(BASELINE_PATH.read_text(encoding="utf-8"))
    base = baseline.get("baseline", {})
    raw = str(base.get("baseline_sha") or base.get("target_commit") or "")
    return "" if raw in {"", "unset"} else raw


def short_sha(sha: str) -> str:
    return sha[:7] if sha else "unknown"


def map_go_benchmarks(go_raw: dict[str, Any]) -> dict[str, dict[str, float]]:
    mapped: dict[str, dict[str, float]] = {}
    for name, metrics in go_raw.items():
        if not isinstance(metrics, dict):
            continue
        mapped[name] = {
            "ns_per_op": float(metrics.get("ns_per_op", 0.0)),
            "allocs_per_op": float(metrics.get("allocs_per_op", 0.0)),
            "bytes_per_op": float(metrics.get("bytes_per_op", 0.0)),
        }
    return mapped


def build_run_record(latest: dict[str, Any], gate: dict[str, Any], baseline_sha: str) -> dict[str, Any]:
    sha = str(latest.get("sha") or os.environ.get("GITHUB_SHA", "local"))
    status = str(gate.get("status") or "unknown")
    regression_pct = gate.get("regression_pct")
    return {
        "sha": sha,
        "short_sha": short_sha(sha),
        "timestamp": str(latest.get("timestamp") or ""),
        "branch": str(latest.get("branch") or "local"),
        "pr_number": latest.get("pr_number"),
        "run_url": str(latest.get("run_url") or ""),
        "go_version": str(latest.get("go_version") or ""),
        "runner_os": str(latest.get("runner") or latest.get("runner_os") or "unknown"),
        "runner_cpu": str(latest.get("runner_cpu") or ""),
        "runner_vcpus": int(latest.get("runner_vcpus") or 2),
        "k6": map_k6(latest.get("k6", {}), OUT_DIR / "k6-summary.json"),
        "stages": map_stages(latest.get("stages", {})),
        "status": status,
        "regression_vs_baseline_pct": regression_pct,
        "baseline_sha": baseline_sha or None,
        "go_benchmarks": map_go_benchmarks(latest.get("go_benchmarks", {})),
    }


def load_previous_runs() -> list[dict[str, Any]]:
    if not PREV_PATH.exists():
        return []
    data = json.loads(PREV_PATH.read_text(encoding="utf-8"))
    return list(data.get("runs", []))


def main() -> int:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    latest = json.loads(LATEST_PATH.read_text(encoding="utf-8"))
    gate = load_gate_result()
    baseline_sha = load_baseline_sha()
    new_run = build_run_record(latest, gate, baseline_sha)

    prev_runs = load_previous_runs()
    runs = [new_run]
    for run in prev_runs:
        if run.get("sha") == new_run.get("sha"):
            continue
        runs.append(run)
    runs = runs[:MAX_RUNS]

    payload = {
        "schema_version": 1,
        "baseline_sha": baseline_sha,
        "runs": runs,
    }
    OUTPUT_PATH.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    print(json.dumps({"ok": True, "runs": len(runs), "status": new_run["status"]}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
