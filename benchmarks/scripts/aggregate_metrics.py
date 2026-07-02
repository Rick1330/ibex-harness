#!/usr/bin/env python3
import json
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


def parse_k6_summary(path: Path):
    data = json.loads(path.read_text(encoding="utf-8"))
    metrics = data.get("metrics", {})
    lat = metrics.get("http_req_duration", {})
    checks = metrics.get("checks", {})
    failed = metrics.get("http_req_failed", {})
    reqs = metrics.get("http_reqs", {})
    return {
        "p50_ms": lat.get("values", {}).get("p(50)", 0.0),
        "p95_ms": lat.get("values", {}).get("p(95)", 0.0),
        "p99_ms": lat.get("values", {}).get("p(99)", 0.0),
        "p999_ms": lat.get("values", {}).get("p(99.9)", 0.0),
        "req_per_s": reqs.get("values", {}).get("rate", 0.0),
        "error_rate": failed.get("values", {}).get("rate", 0.0),
        "check_rate": checks.get("values", {}).get("rate", 0.0),
    }


def parse_runner_cpu():
    return platform.processor() or platform.machine()


def stage_breakdown(go_bench):
    def ns_to_ms(v):
        return v / 1_000_000.0

    auth = go_bench.get("BenchmarkStageAuth", {}).get("ns_per_op", 0.0)
    rl = go_bench.get("BenchmarkStageRateLimit", {}).get("ns_per_op", 0.0)
    dr = go_bench.get("BenchmarkStageDirectiveResolve", {}).get("ns_per_op", 0.0)
    pi = go_bench.get("BenchmarkStagePromptInject", {}).get("ns_per_op", 0.0)
    total = go_bench.get("BenchmarkProxyOverhead", {}).get("ns_per_op", 0.0)
    return {
        "auth_lru_p99_ms": ns_to_ms(auth),
        "rate_limit_p99_ms": ns_to_ms(rl),
        "directive_resolve_p99_ms": ns_to_ms(dr),
        "prompt_inject_p99_ms": ns_to_ms(pi),
        "total_overhead_p99_ms": ns_to_ms(total),
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

    # machine-readable summary for downstream steps
    print(json.dumps({"ok": True, "p99_ms": k6["p99_ms"], "error_rate": k6["error_rate"]}))
    return 0


if __name__ == "__main__":
    sys.exit(main())
