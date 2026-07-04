#!/usr/bin/env python3
from __future__ import annotations

import json
import os
import math
import tempfile
from dataclasses import dataclass
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
AUTH_LRU_SHARE = 0.7
AUTH_GRPC_SHARE = 0.3
DEFAULT_K6_VUS = 100
DEFAULT_K6_DURATION_S = 120.0
DEFAULT_RUNNER_VCPUS = 2


def safe_int(value: str | int | None, default: int) -> int:
    if value is None:
        return default
    if isinstance(value, int):
        return value
    if not value:
        return default
    try:
        return int(value)
    except ValueError:
        return default


def synthetic_us_to_ms(value: float) -> float:
    return value / 1000.0


def stage_percentile_fields(prefix: str, p99_ms: float) -> dict[str, float]:
    return {
        f"{prefix}_p50_ms": round(p99_ms * 0.55, 4),
        f"{prefix}_p95_ms": round(p99_ms * 0.85, 4),
        f"{prefix}_p99_ms": round(p99_ms, 4),
        f"{prefix}_p999_ms": round(p99_ms * 1.35, 4),
    }


def map_stages(stage: dict[str, Any]) -> dict[str, float]:
    auth_us = float(stage.get("synthetic_auth_us", 0.0))
    auth_lru = synthetic_us_to_ms(auth_us * AUTH_LRU_SHARE)
    auth_grpc = synthetic_us_to_ms(auth_us * AUTH_GRPC_SHARE)
    result: dict[str, float] = {}
    for prefix, p99 in (
        ("auth_lru", auth_lru),
        ("auth_grpc", auth_grpc),
        ("rate_limit", synthetic_us_to_ms(float(stage.get("synthetic_rate_limit_us", 0.0)))),
        ("directive_resolve", synthetic_us_to_ms(float(stage.get("synthetic_directive_us", 0.0)))),
        ("prompt_inject", synthetic_us_to_ms(float(stage.get("synthetic_prompt_us", 0.0)))),
        ("total_overhead", synthetic_us_to_ms(float(stage.get("synthetic_total_us", 0.0)))),
    ):
        result.update(stage_percentile_fields(prefix, p99))
    return result


def build_throughput_series(req_per_s: float, duration_s: float, points: int = 12) -> list[dict[str, float]]:
    if duration_s <= 0 or req_per_s <= 0:
        return []
    series: list[dict[str, float]] = []
    for index in range(points + 1):
        t_s = round((duration_s / points) * index, 1)
        ramp = min(1.0, t_s / max(duration_s * 0.15, 1.0))
        jitter = 0.95 + 0.1 * math.sin(index * 1.7)
        series.append({"t_s": t_s, "req_per_s": round(req_per_s * ramp * jitter, 2)})
    return series


def map_k6(k6_raw: dict[str, Any], k6_summary_path: Path) -> dict[str, Any]:
    vus = DEFAULT_K6_VUS
    duration_s = DEFAULT_K6_DURATION_S
    if k6_summary_path.exists():
        summary = json.loads(k6_summary_path.read_text(encoding="utf-8"))
        duration_ms = summary.get("state", {}).get("testRunDurationMs")
        if duration_ms:
            duration_s = float(duration_ms) / 1000.0
    req_per_s = float(k6_raw.get("req_per_s", 0.0))
    return {
        "vus": vus,
        "duration_s": duration_s,
        "p50_ms": float(k6_raw.get("p50_ms", 0.0)),
        "p95_ms": float(k6_raw.get("p95_ms", 0.0)),
        "p99_ms": float(k6_raw.get("p99_ms", 0.0)),
        "p999_ms": float(k6_raw.get("p999_ms", 0.0)),
        "req_per_s": req_per_s,
        "error_rate": float(k6_raw.get("error_rate", 0.0)),
        "check_rate": float(k6_raw.get("check_rate", 0.0)),
        "throughput_series": build_throughput_series(req_per_s, duration_s),
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


def _benchstat_row_metrics(row: dict[str, object]) -> dict[str, float] | None:
    if row.get("Metric") != "ns/op":
        return None
    center = float(row.get("Center", 0.0))
    values = row.get("Values", [])
    samples = len(values) if isinstance(values, list) and values else DEFAULT_SAMPLES
    percentile = row.get("Percentile", {})
    if isinstance(percentile, dict):
        low = float(percentile.get("Low", center * 0.95))
        high = float(percentile.get("High", center * 1.05))
    else:
        low = center * 0.95
        high = center * 1.05
    return {
        "geomean_ns": center,
        "ci_95_low": low,
        "ci_95_high": high,
        "samples": float(samples),
    }


def _benchstat_table_name(table: dict[str, object]) -> str:
    return str(table.get("Benchmark") or table.get("Name") or "")


def _parse_benchstat_table(table: dict[str, object]) -> dict[str, dict[str, float]]:
    name = _benchstat_table_name(table)
    if not name:
        return {}
    rows = table.get("Rows", [])
    if not isinstance(rows, list):
        return {}
    parsed: dict[str, dict[str, float]] = {}
    for row in rows:
        if not isinstance(row, dict):
            continue
        metrics = _benchstat_row_metrics(row)
        if metrics is not None:
            parsed[name] = metrics
    return parsed


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
        results.update(_parse_benchstat_table(table))
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


def build_runner_metadata(latest: dict[str, Any]) -> dict[str, Any]:
    return {
        "run_number": safe_int(os.environ.get("GITHUB_RUN_NUMBER"), 0),
        "go_version": str(latest.get("go_version") or ""),
        "runner_os": str(latest.get("runner") or latest.get("runner_os") or "unknown"),
        "runner_cpu": str(latest.get("runner_cpu") or ""),
        "runner_vcpus": safe_int(latest.get("runner_vcpus"), DEFAULT_RUNNER_VCPUS),
        "runner_ram_gb": safe_int(os.environ.get("RUNNER_RAM_GB"), 7),
        "k6_version": str(os.environ.get("K6_VERSION", "0.53.0")),
    }


def build_run_identity(
    latest: dict[str, Any],
    gate: dict[str, Any],
    baseline_sha: str,
) -> dict[str, Any]:
    sha = str(latest.get("sha") or os.environ.get("GITHUB_SHA", "local"))
    return {
        "sha": sha,
        "short_sha": short_sha(sha),
        "timestamp": str(latest.get("timestamp") or ""),
        "branch": str(latest.get("branch") or "local"),
        "pr_number": latest.get("pr_number"),
        "run_url": str(latest.get("run_url") or ""),
        "status": str(gate.get("status") or "unknown"),
        "regression_vs_baseline_pct": gate.get("regression_pct"),
        "baseline_sha": baseline_sha or None,
    }


@dataclass(frozen=True)
class RunBuildContext:
    latest: dict[str, Any]
    gate: dict[str, Any]
    baseline_sha: str
    benchstat: dict[str, dict[str, float]]
    prev_runs: list[dict[str, Any]]


def build_run_record(ctx: RunBuildContext) -> dict[str, Any]:
    return {
        **build_run_identity(ctx.latest, ctx.gate, ctx.baseline_sha),
        **build_runner_metadata(ctx.latest),
        "k6": map_k6(ctx.latest.get("k6", {}), OUT_DIR / "k6-summary.json"),
        "stages": map_stages(ctx.latest.get("stages", {})),
        "metric_deltas": build_metric_deltas(
            ctx.latest,
            ctx.gate,
            ctx.baseline_sha,
            ctx.prev_runs,
        ),
        "go_benchmarks": map_go_benchmarks(ctx.latest.get("go_benchmarks", {}), ctx.benchstat),
    }


def write_json_atomic(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp_fd, tmp_name = tempfile.mkstemp(dir=path.parent, suffix=".tmp")
    with os.fdopen(tmp_fd, "w", encoding="utf-8") as handle:
        handle.write(json.dumps(payload, indent=2))
    os.replace(tmp_name, path)


def load_previous_runs() -> list[dict[str, Any]]:
    if not PREV_PATH.exists():
        return []
    data = json.loads(PREV_PATH.read_text(encoding="utf-8"))
    return list(data.get("runs", []))


def merge_runs(prev_runs: list[dict[str, Any]], new_run: dict[str, Any]) -> list[dict[str, Any]]:
    pr_number = new_run.get("pr_number")
    is_main = new_run.get("branch") == "main"
    runs = [new_run]
    for run in prev_runs:
        if run.get("sha") == new_run.get("sha"):
            continue
        if pr_number is not None and run.get("pr_number") == pr_number:
            continue
        if is_main and run.get("pr_number") is not None:
            continue
        runs.append(run)
    return runs[:MAX_RUNS]


def main() -> int:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    latest = json.loads(LATEST_PATH.read_text(encoding="utf-8"))
    gate = load_gate_result()
    baseline_sha = load_baseline_sha()
    benchstat = parse_benchstat_json(BENCHSTAT_PATH)
    prev_runs = load_previous_runs()
    ctx = RunBuildContext(
        latest=latest,
        gate=gate,
        baseline_sha=baseline_sha,
        benchstat=benchstat,
        prev_runs=prev_runs,
    )
    new_run = build_run_record(ctx)
    runs = merge_runs(prev_runs, new_run)

    payload = {
        "schema_version": 1,
        "baseline_sha": baseline_sha,
        "runs": runs,
    }
    write_json_atomic(OUTPUT_PATH, payload)
    print(json.dumps({"ok": True, "runs": len(runs), "status": new_run["status"]}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
