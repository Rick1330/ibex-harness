#!/usr/bin/env python3
"""Regression gate for ranking-quality benchmark output."""

from __future__ import annotations

import json
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


def main() -> int:
    latest = load_json(LATEST_PATH)
    baseline_raw = load_json(BASELINE_PATH)
    policy = baseline_raw.get("policy", {})
    baseline_metrics = baseline_raw.get("baseline", {})
    if not isinstance(baseline_metrics, dict):
        print("baseline.baseline must be an object", file=sys.stderr)
        return 1

    max_reg = read_float(policy.get("max_regression_pct"), 5.0)
    latest_metrics = latest.get("metrics", {})
    if not isinstance(latest_metrics, dict):
        print("latest.metrics must be an object", file=sys.stderr)
        return 1

    float_metrics = {
        k: parse_finite_float(v) for k, v in baseline_metrics.items()
    }
    latest_float = {
        k: parse_finite_float(latest_metrics.get(k)) for k in float_metrics
    }
    checks = build_metric_checks(
        latest_float,
        float_metrics,
        max_regression_pct=max_reg,
        higher_is_better=True,
    )
    ok, check_lines = format_check_lines(checks)
    summary = [
        "## Ranking-quality regression gate",
        "",
        f"- precision@5: {(latest_float.get('precision_at_5') or 0):.4f}",
        f"- recall@10: {(latest_float.get('recall_at_10') or 0):.4f}",
        f"- mrr: {(latest_float.get('mrr') or 0):.4f}",
        "",
        *check_lines,
        "",
    ]
    text = "\n".join(summary)
    print(text)
    write_gate_result(GATE_RESULT_PATH, ok, checks)
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
