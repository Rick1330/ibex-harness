"""Shared regression-gate comparison for memory benchmarks."""

from __future__ import annotations

import json
import math
from pathlib import Path
from typing import Any

Check = tuple[str, float, float, bool]


def parse_finite_float(value: object) -> float | None:
    """Parse a metric value; return None when missing or non-finite."""
    if value is None:
        return None
    try:
        parsed = float(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return None
    if not math.isfinite(parsed):
        return None
    return parsed


def read_float(value: object, default: float = 0.0) -> float:
    """Legacy helper — prefer parse_finite_float for gate checks."""
    parsed = parse_finite_float(value)
    return default if parsed is None else parsed


def pct_change(cur: float, base: float) -> float:
    if base == 0:
        return 0.0
    return ((cur - base) / base) * 100.0


def load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def build_metric_checks(
    latest_metrics: dict[str, float | None],
    baseline_metrics: dict[str, float | None],
    *,
    max_regression_pct: float,
    higher_is_better: bool = True,
) -> list[Check]:
    checks: list[Check] = []
    for name, base_raw in baseline_metrics.items():
        cur_raw = latest_metrics.get(name)
        cur_val = parse_finite_float(cur_raw)
        base_val = parse_finite_float(base_raw)
        if cur_val is None:
            checks.append((f"{name} present", 0.0, 1.0, False))
            continue
        if base_val is None:
            checks.append((f"{name} baseline valid", 0.0, 1.0, False))
            continue
        if base_val == 0:
            checks.append((f"{name} regression (%)", 0.0, max_regression_pct, True))
            continue
        change = pct_change(cur_val, base_val)
        if higher_is_better:
            regressed = change < -max_regression_pct
            limit = -max_regression_pct
        else:
            regressed = change > max_regression_pct
            limit = max_regression_pct
        checks.append((f"{name} regression (%)", change, limit, not regressed))
    return checks


def format_check_lines(checks: list[Check]) -> tuple[bool, list[str]]:
    summary_lines = ["### Checks"]
    ok = True
    for name, cur, lim, passed in checks:
        mark = "PASS" if passed else "FAIL"
        summary_lines.append(f"- {mark}: {name} (value={cur:.6f}, limit={lim:.6f})")
        ok = ok and passed
    return ok, summary_lines


def write_gate_result(path: Path, ok: bool, checks: list[Check]) -> None:
    payload = {
        "status": "pass" if ok else "fail",
        "checks": [
            {"name": name, "value": cur, "limit": lim, "ok": passed}
            for name, cur, lim, passed in checks
        ],
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
