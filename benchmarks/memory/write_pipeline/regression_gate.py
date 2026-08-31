#!/usr/bin/env python3
"""Regression gate for write-pipeline benchmark (p95 SLA + baseline)."""

from __future__ import annotations

import sys
from pathlib import Path

_BENCH_MEMORY = Path(__file__).resolve().parents[1]
if str(_BENCH_MEMORY) not in sys.path:
    sys.path.insert(0, str(_BENCH_MEMORY))

from regression_gate_common import (  # noqa: E402
    build_metric_checks,
    format_check_lines,
    load_json,
    parse_finite_float,
    read_float,
    write_gate_result,
)

_DIR = Path(__file__).resolve().parent
LATEST_PATH = _DIR / "output" / "latest.json"
BASELINE_PATH = _DIR / "baseline.json"
GATE_RESULT_PATH = _DIR / "output" / "gate-result.json"

Check = tuple[str, float, float, bool]


def main() -> int:
    latest = load_json(LATEST_PATH)
    baseline_raw = load_json(BASELINE_PATH)
    policy = baseline_raw.get("policy", {})
    baseline_metrics = baseline_raw.get("baseline", {})
    latest_metrics = latest.get("metrics", {})
    if not isinstance(baseline_metrics, dict) or not isinstance(latest_metrics, dict):
        print("baseline and latest metrics must be objects", file=sys.stderr)
        return 1

    max_reg = read_float(policy.get("max_regression_pct"), 20.0)
    max_p95 = read_float(policy.get("max_latency_ms_p95"), 200.0)

    p95_raw = parse_finite_float(latest_metrics.get("latency_ms_p95"))
    base_p95_raw = parse_finite_float(baseline_metrics.get("latency_ms_p95"))
    p95 = p95_raw if p95_raw is not None else 0.0
    base_p95 = base_p95_raw if base_p95_raw is not None else 0.0

    checks: list[Check] = [
        (
            "p95 SLA (ms)",
            p95,
            max_p95,
            p95_raw is not None and p95 > 0.0 and p95 <= max_p95,
        ),
    ]
    reg_checks = build_metric_checks(
        {"latency_ms_p95": p95_raw},
        {"latency_ms_p95": base_p95_raw},
        max_regression_pct=max_reg,
        higher_is_better=False,
    )
    checks.extend(reg_checks)

    ok, check_lines = format_check_lines(checks)
    summary = [
        "## Write-pipeline regression gate",
        "",
        f"- p50: {read_float(latest_metrics.get('latency_ms_p50')):.2f} ms",
        f"- p95: {p95:.2f} ms (SLA <= {max_p95:.0f} ms)",
        f"- p99: {read_float(latest_metrics.get('latency_ms_p99')):.2f} ms",
        "",
        *check_lines,
        "",
    ]
    print("\n".join(summary))
    write_gate_result(GATE_RESULT_PATH, ok, checks)
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
