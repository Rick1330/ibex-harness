#!/usr/bin/env python3
import json
import math
import os
import platform
import sys
from datetime import datetime, timezone
from pathlib import Path


def safe_int(value: str, default: int) -> int:
    try:
        return int(value)
    except ValueError:
        return default


def parse_go_bench(path: Path):
    bench = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        row = parse_go_bench_line(line)
        if row is None:
            continue
        bench[row["name"]] = row["metrics"]
    return bench


def parse_go_bench_line(line: str):
    if not line.startswith("Benchmark"):
        return None
    fields = line.split()
    if len(fields) < 4:
        return None
    try:
        ns = float(fields[2])
    except ValueError:
        return None

    return {
        "name": fields[0].split("-")[0],
        "metrics": {
            "ns_per_op": ns,
            "bytes_per_op": read_metric(fields, "B/op"),
            "allocs_per_op": read_metric(fields, "allocs/op"),
        },
    }


def read_metric(fields, unit):
    for idx in range(1, len(fields)):
        if fields[idx] != unit:
            continue
        try:
            return float(fields[idx - 1])
        except ValueError:
            return 0.0
    return 0.0


def metric_values(metrics: dict, name: str) -> dict:
    """Return metric fields for legacy (values wrapper) and k6 0.53 flat exports."""
    raw = metrics.get(name, {})
    if not isinstance(raw, dict):
        return {}
    nested = raw.get("values")
    if isinstance(nested, dict):
        return nested
    return raw


def read_trend_ms(values: dict, *keys: str) -> float:
    for key in keys:
        if key in values:
            try:
                return float(values[key])
            except (TypeError, ValueError):
                continue
    return 0.0


def _optional_float(values: dict, key: str) -> float | None:
    if key not in values:
        return None
    try:
        return float(values[key])
    except (TypeError, ValueError):
        return None


def read_rate(values: dict) -> float:
    rate = _optional_float(values, "rate")
    if rate is not None:
        return rate
    value = _optional_float(values, "value")
    return value if value is not None else 0.0


def derive_req_rate(reqs: dict, data: dict, base_rate: float) -> float:
    if not math.isclose(base_rate, 0.0, abs_tol=1e-12):
        return base_rate
    count = reqs.get("count")
    duration_ms = data.get("state", {}).get("testRunDurationMs")
    if not count or not duration_ms:
        return base_rate
    duration_s = float(duration_ms) / 1000.0
    if duration_s <= 0:
        return base_rate
    return float(count) / duration_s


def parse_k6_summary(path: Path):
    data = json.loads(path.read_text(encoding="utf-8"))
    metrics = data.get("metrics", {})
    if isinstance(metrics, list):
        metrics = {entry.get("name", ""): entry for entry in metrics if isinstance(entry, dict)}

    lat = metric_values(metrics, "http_req_duration")
    checks = metric_values(metrics, "checks")
    failed = metric_values(metrics, "http_req_failed")
    reqs = metric_values(metrics, "http_reqs")

    req_rate = derive_req_rate(reqs, data, read_rate(reqs))

    return {
        "p50_ms": read_trend_ms(lat, "p(50)", "med"),
        "p95_ms": read_trend_ms(lat, "p(95)"),
        "p99_ms": read_trend_ms(lat, "p(99)"),
        "p999_ms": read_trend_ms(lat, "p(99.9)"),
        "req_per_s": req_rate,
        "error_rate": read_rate(failed),
        "check_rate": read_rate(checks),
    }


def parse_runner_cpu():
    return platform.processor() or platform.machine()


def stage_breakdown(go_bench):
    def ns_to_us(v):
        return v / 1_000.0

    return {
        "synthetic_auth_us": ns_to_us(go_bench.get("BenchmarkStageAuth", {}).get("ns_per_op", 0.0)),
        "synthetic_rate_limit_us": ns_to_us(go_bench.get("BenchmarkStageRateLimit", {}).get("ns_per_op", 0.0)),
        "synthetic_directive_us": ns_to_us(go_bench.get("BenchmarkStageDirectiveResolve", {}).get("ns_per_op", 0.0)),
        "synthetic_prompt_us": ns_to_us(go_bench.get("BenchmarkStagePromptInject", {}).get("ns_per_op", 0.0)),
        "synthetic_total_us": ns_to_us(go_bench.get("BenchmarkProxyOverhead", {}).get("ns_per_op", 0.0)),
        "proxy_health_us": ns_to_us(go_bench.get("BenchmarkProxyHealth", {}).get("ns_per_op", 0.0)),
    }


def load_runs(path: Path):
    if not path.exists():
        return []
    data = json.loads(path.read_text(encoding="utf-8"))
    return data.get("runs", [])


def main():
    out_dir = Path("benchmarks/output")
    out_dir.mkdir(parents=True, exist_ok=True)

    go_bench = parse_go_bench(out_dir / "go-bench.txt")
    k6 = parse_k6_summary(out_dir / "k6-summary.json")
    stage = stage_breakdown(go_bench)

    sha = os.environ.get("GITHUB_SHA", "local")
    branch = os.environ.get("GITHUB_REF_NAME", "local")
    run_url = os.environ.get("RUN_URL", "")
    go_ver = os.environ.get("GO_VERSION", "")

    run = {
        "sha": sha,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "branch": branch,
        "run_url": run_url,
        "go_version": go_ver,
        "runner": os.environ.get("RUNNER_OS", "unknown"),
        "runner_cpu": parse_runner_cpu(),
        "runner_vcpus": safe_int(os.environ.get("RUNNER_VCPU", "2"), default=2),
        "go_benchmarks": go_bench,
        "k6": k6,
        "stages": stage,
    }

    prev_runs = load_runs(out_dir / "prev-runs.json")
    runs = [run] + prev_runs
    runs = runs[:200]
    (out_dir / "runs.json").write_text(json.dumps({"runs": runs}, indent=2), encoding="utf-8")
    (out_dir / "latest.json").write_text(json.dumps(run, indent=2), encoding="utf-8")

    print(json.dumps({"ok": True, "p99_ms": k6["p99_ms"], "error_rate": k6["error_rate"]}))
    return 0


if __name__ == "__main__":
    sys.exit(main())
