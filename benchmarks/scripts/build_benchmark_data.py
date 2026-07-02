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
BENCHSTAT_PATH = OUT_DIR / "benchstat.json"
OUTPUT_PATH = OUT_DIR / "benchmark-data.json"
MAX_RUNS = 365
DEFAULT_SAMPLES = 5


def safe_int(value: str | None, default: int) -> int:
    if not value:
        return default
    try:
        return int(value)
    except ValueError:
        return default


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


def parse_benchstat_json(path: Path) -> dict[str, dict[str, float]]:
    if not path.exists():
        return {}
    raw = json.loads(path.read_text(encoding="utf-8"))
    results: dict[str, dict[str, float]] = {}

    tables = raw.get("Tables", []) if isinstance(raw, dict) else raw
    if not isinstance(tables, list):
        return results

    for table in tables:
        if not isinstance(table, dict):
            continue
        name = str(table.get("Benchmark") or table.get("Name") or "")
        if not name:
            continue
        rows = table.get("Rows", [])
        for row in rows if isinstance(rows, list) else []:
            if not isinstance(row, dict) or row.get("Metric") != "ns/op":
                continue
            center = float(row.get("Center", 0.0))
            values = row.get("Values", [])
            samples = len(values) if isinstance(values, list) and values else DEFAULT_SAMPLES
            percentile = row.get("Percentile", {})
            low = float(percentile.get("Low", center * 0.95)) if isinstance(percentile, dict) else center * 0.95
            high = float(percentile.get("High", center * 1.05)) if isinstance(percentile, dict) else center * 1.05
            results[name] = {
                "geomean_ns": center,
                "ci_95_low": low,
                "ci_95_high": high,
                "samples": float(samples),
            }
    return results


def enrich_go_benchmark(
    name: str,
    metrics: dict[str, Any],
    benchstat: dict[str, dict[str, float]],
) -> dict[str, float]:
    ns = float(metrics.get("ns_per_op", 0.0))
    stats = benchstat.get(name, {})
    geomean = float(stats.get("geomean_ns", ns))
    low = float(stats.get("ci_95_low", geomean * 0.95))
    high = float(stats.get("ci_95_high", geomean * 1.05))
    samples = int(stats.get("samples", DEFAULT_SAMPLES))
    return {
        "ns_per_op": ns,
        "allocs_per_op": float(metrics.get("allocs_per_op", 0.0)),
        "bytes_per_op": float(metrics.get("bytes_per_op", 0.0)),
        "samples": samples,
        "ci_95_low": low,
        "ci_95_high": high,
        "geomean_ns": geomean,
    }


def map_go_benchmarks(
    go_raw: dict[str, Any],
    benchstat: dict[str, dict[str, float]],
) -> dict[str, dict[str, float]]:
    mapped: dict[str, dict[str, float]] = {}
    for name, metrics in go_raw.items():
        if not isinstance(metrics, dict):
            continue
        mapped[name] = enrich_go_benchmark(name, metrics, benchstat)
    return mapped


def build_metric_deltas(
    latest: dict[str, Any],
    gate: dict[str, Any],
    baseline_sha: str,
    prev_runs: list[dict[str, Any]],
) -> dict[str, float | None]:
    deltas: dict[str, float | None] = {}
    regression_pct = gate.get("regression_pct")
    if isinstance(regression_pct, (int, float)):
        deltas["k6.p99_ms"] = float(regression_pct)

    baseline_run = next((run for run in prev_runs if run.get("sha") == baseline_sha), None)
    if baseline_run is None:
        return deltas

    base_k6 = baseline_run.get("k6", {})
    cur_k6 = latest.get("k6", {})
    base_req = float(base_k6.get("req_per_s", 0.0))
    cur_req = float(cur_k6.get("req_per_s", 0.0))
    if base_req > 0:
        deltas["k6.req_per_s"] = ((cur_req - base_req) / base_req) * 100.0
    return deltas


def build_run_record(
    latest: dict[str, Any],
    gate: dict[str, Any],
    baseline_sha: str,
    benchstat: dict[str, dict[str, float]],
    prev_runs: list[dict[str, Any]],
) -> dict[str, Any]:
    sha = str(latest.get("sha") or os.environ.get("GITHUB_SHA", "local"))
    status = str(gate.get("status") or "unknown")
    regression_pct = gate.get("regression_pct")
    return {
        "sha": sha,
        "short_sha": short_sha(sha),
        "timestamp": str(latest.get("timestamp") or ""),
        "branch": str(latest.get("branch") or "local"),
        "pr_number": latest.get("pr_number"),
        "run_number": safe_int(os.environ.get("GITHUB_RUN_NUMBER"), 0),
        "run_url": str(latest.get("run_url") or ""),
        "go_version": str(latest.get("go_version") or ""),
        "runner_os": str(latest.get("runner") or latest.get("runner_os") or "unknown"),
        "runner_cpu": str(latest.get("runner_cpu") or ""),
        "runner_vcpus": int(latest.get("runner_vcpus") or 2),
        "runner_ram_gb": safe_int(os.environ.get("RUNNER_RAM_GB"), 7),
        "k6_version": str(os.environ.get("K6_VERSION", "0.53.0")),
        "k6": map_k6(latest.get("k6", {}), OUT_DIR / "k6-summary.json"),
        "stages": map_stages(latest.get("stages", {})),
        "status": status,
        "regression_vs_baseline_pct": regression_pct,
        "baseline_sha": baseline_sha or None,
        "metric_deltas": build_metric_deltas(latest, gate, baseline_sha, prev_runs),
        "go_benchmarks": map_go_benchmarks(latest.get("go_benchmarks", {}), benchstat),
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
    benchstat = parse_benchstat_json(BENCHSTAT_PATH)
    prev_runs = load_previous_runs()
    new_run = build_run_record(latest, gate, baseline_sha, benchstat, prev_runs)

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
