#!/usr/bin/env python3
from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

LATEST_PATH = Path("benchmarks/output/latest.json")
BASELINE_PATH = Path("benchmarks/data-schema/baseline.json")
GATE_RESULT_PATH = Path("benchmarks/output/gate-result.json")

Check = tuple[str, float, float, bool]


def read_float(value: object, default: float = 0.0) -> float:
    try:
        return float(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return default


def pct_change(cur: float, base: float) -> float:
    if base == 0:
        return 0.0
    return ((cur - base) / base) * 100.0


def load_inputs() -> tuple[dict[str, Any], dict[str, Any]]:
    latest_raw = json.loads(LATEST_PATH.read_text(encoding="utf-8"))
    baseline_raw = json.loads(BASELINE_PATH.read_text(encoding="utf-8"))
    latest = normalize_latest(latest_raw)
    baseline = normalize_baseline(baseline_raw)
    return latest, baseline


def normalize_latest(raw: dict[str, Any]) -> dict[str, Any]:
    k6_raw = raw.get("k6", {})
    go_raw = raw.get("go_benchmarks", {}).get("BenchmarkProxyOverhead", {})
    stage_raw = raw.get("stages", {})
    return {
        "k6": {
            "p99_ms": read_float(k6_raw.get("p99_ms")),
            "req_per_s": read_float(k6_raw.get("req_per_s")),
            "error_rate": read_float(k6_raw.get("error_rate")),
            "check_rate": read_float(k6_raw.get("check_rate")),
        },
        "go_benchmarks": {
            "BenchmarkProxyOverhead": {
                "allocs_per_op": read_float(go_raw.get("allocs_per_op")),
                "bytes_per_op": read_float(go_raw.get("bytes_per_op")),
            }
        },
        "stages": {
            "synthetic_total_us": read_float(stage_raw.get("synthetic_total_us")),
        },
    }


def normalize_baseline(raw: dict[str, Any]) -> dict[str, Any]:
    policy_raw = raw.get("policy", {})
    base_raw = raw.get("baseline", {})
    return {
        "policy": {
            "max_proxy_overhead_p99_ms": read_float(policy_raw.get("max_proxy_overhead_p99_ms"), 20.0),
            "max_error_rate": read_float(policy_raw.get("max_error_rate"), 0.001),
            "max_regression_pct": read_float(policy_raw.get("max_regression_pct"), 20.0),
        },
        "baseline": {
            "proxy_overhead_p99_ms": read_float(base_raw.get("proxy_overhead_p99_ms")),
        },
    }


def build_checks(latest: dict[str, Any], baseline: dict[str, Any]) -> list[Check]:
    policy = baseline["policy"]
    base = baseline["baseline"]
    k6 = latest["k6"]
    checks: list[Check] = []
    checks.append(
        (
            "k6 throughput present",
            k6["req_per_s"],
            1.0,
            k6["req_per_s"] > 0.0,
        )
    )
    checks.append(
        (
            "k6 checks passing",
            k6.get("check_rate", 0.0),
            0.99,
            k6.get("check_rate", 0.0) >= 0.99,
        )
    )
    checks.append(
        (
            "k6 p99 SLA",
            k6["p99_ms"],
            policy["max_proxy_overhead_p99_ms"],
            k6["p99_ms"] > 0.0 and k6["p99_ms"] <= policy["max_proxy_overhead_p99_ms"],
        )
    )
    checks.append(("error rate", k6["error_rate"], policy["max_error_rate"], k6["error_rate"] <= policy["max_error_rate"]))
    if base["proxy_overhead_p99_ms"] > 0:
        reg = pct_change(k6["p99_ms"], base["proxy_overhead_p99_ms"])
        checks.append(("regression vs baseline (%)", reg, policy["max_regression_pct"], reg <= policy["max_regression_pct"]))
    return checks


def format_check_lines(checks: list[Check]) -> tuple[bool, list[str]]:
    summary_lines = ["### Checks"]
    ok = True
    for name, cur, lim, passed in checks:
        mark = "PASS" if passed else "FAIL"
        summary_lines.append(f"- {mark}: {name} (value={cur:.6f}, limit={lim:.6f})")
        ok = ok and passed
    return ok, summary_lines


def find_regression_pct(checks: list[Check]) -> float | None:
    for name, cur, _, _ in checks:
        if name == "regression vs baseline (%)":
            return cur
    return None


def build_summary_lines(latest: dict[str, Any], checks: list[Check]) -> tuple[bool, list[str], float | None]:
    stage = latest["stages"]
    go_bench = latest["go_benchmarks"].get("BenchmarkProxyOverhead", {})
    allocs = float(go_bench.get("allocs_per_op", 0.0))
    bytes_op = float(go_bench.get("bytes_per_op", 0.0))
    k6 = latest["k6"]

    summary_lines = [
        "## Benchmark regression gate",
        "",
        f"- p99: {k6['p99_ms']:.3f} ms",
        f"- req/s: {k6['req_per_s']:.2f}",
        f"- error rate: {k6['error_rate']:.6f}",
        f"- allocs/op: {allocs:.3f}",
        f"- bytes/op: {bytes_op:.3f}",
        f"- stage synthetic total: {stage['synthetic_total_us']:.3f} µs",
        "",
    ]
    ok, check_lines = format_check_lines(checks)
    summary_lines.extend(check_lines)
    return ok, summary_lines, find_regression_pct(checks)


def resolve_gate_status(ok: bool, regression_pct: float | None) -> str:
    if not ok:
        return "fail"
    if regression_pct is not None and regression_pct > 5.0:
        return "regression"
    return "pass"


def write_gate_result(ok: bool, checks: list[Check], regression_pct: float | None) -> None:
    payload = {
        "status": resolve_gate_status(ok, regression_pct),
        "regression_pct": regression_pct,
        "checks": [
            {"name": name, "value": cur, "limit": lim, "ok": passed}
            for name, cur, lim, passed in checks
        ],
    }
    GATE_RESULT_PATH.parent.mkdir(parents=True, exist_ok=True)
    GATE_RESULT_PATH.write_text(json.dumps(payload, indent=2), encoding="utf-8")


def main() -> int:
    latest, baseline = load_inputs()
    checks = build_checks(latest, baseline)
    ok, summary_lines, regression_pct = build_summary_lines(latest, checks)
    write_gate_result(ok, checks, regression_pct)
    summary_text = "\n".join(summary_lines) + "\n"
    print(summary_text)

    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
