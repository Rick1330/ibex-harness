#!/usr/bin/env python3
import json
import sys
from pathlib import Path


def pct_change(cur, base):
    if base == 0:
        return 0.0
    return ((cur - base) / base) * 100.0


def main():
    out = Path("benchmarks/output")
    latest = json.loads((out / "latest.json").read_text(encoding="utf-8"))
    baseline = json.loads(Path("benchmarks/data-schema/baseline.json").read_text(encoding="utf-8"))

    policy = baseline["policy"]
    base = baseline["baseline"]
    k6 = latest["k6"]
    stage = latest["stages"]
    go_bench = latest["go_benchmarks"].get("BenchmarkProxyOverhead", {})

    checks = []
    checks.append(
        (
            "k6 p99 SLA",
            k6["p99_ms"],
            policy["max_proxy_overhead_p99_ms"],
            k6["p99_ms"] <= policy["max_proxy_overhead_p99_ms"],
        )
    )
    checks.append(("error rate", k6["error_rate"], policy["max_error_rate"], k6["error_rate"] <= policy["max_error_rate"]))

    if base["proxy_overhead_p99_ms"] > 0:
        reg = pct_change(k6["p99_ms"], base["proxy_overhead_p99_ms"])
        checks.append(("regression vs baseline (%)", reg, policy["max_regression_pct"], reg <= policy["max_regression_pct"]))

    allocs = float(go_bench.get("allocs_per_op", 0.0))
    bytes_op = float(go_bench.get("bytes_per_op", 0.0))

    summary_lines = [
        "## Benchmark regression gate",
        "",
        f"- p99: {k6['p99_ms']:.3f} ms",
        f"- req/s: {k6['req_per_s']:.2f}",
        f"- error rate: {k6['error_rate']:.6f}",
        f"- allocs/op: {allocs:.3f}",
        f"- bytes/op: {bytes_op:.3f}",
        f"- stage total overhead: {stage['total_overhead_p99_ms']:.3f} ms",
        "",
        "### Checks",
    ]

    ok = True
    for name, cur, lim, passed in checks:
        mark = "PASS" if passed else "FAIL"
        summary_lines.append(f"- {mark}: {name} (value={cur:.6f}, limit={lim:.6f})")
        ok = ok and passed

    summary_path = out / "gate-summary.md"
    summary_path.write_text("\n".join(summary_lines) + "\n", encoding="utf-8")
    print(summary_path.read_text(encoding="utf-8"))

    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
