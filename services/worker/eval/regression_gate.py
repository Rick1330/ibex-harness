#!/usr/bin/env python3
"""Regression gate for extraction quality eval (absolute percentage points).

CI-enforced provider blocks only (baseline providers.*.enforcement == \"ci\").
Fails the process (exit 1) when any gated metric drops by more than
policy.max_regression_pp absolute percentage points (default 3.0).

Manual/vLLM blocks are printed for side-by-side visibility but never fail CI.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

_DIR = Path(__file__).resolve().parent
LATEST_PATH = _DIR / "output" / "latest.json"
BASELINE_PATH = _DIR / "gold_set" / "v1" / "baseline_results.json"
GATE_RESULT_PATH = _DIR / "output" / "gate-result.json"


def _parse_float(value: object) -> float | None:
    if value is None:
        return None
    try:
        parsed = float(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return None
    if parsed != parsed:  # NaN
        return None
    return parsed


def _pp_drop(cur: float, base: float) -> float:
    """Absolute percentage-point drop (positive means regression for higher-is-better)."""
    return (base - cur) * 100.0


def evaluate_gate(
    latest: dict[str, Any],
    baseline: dict[str, Any],
) -> tuple[bool, list[dict[str, Any]], list[str]]:
    policy = baseline.get("policy") or {}
    max_pp = _parse_float(policy.get("max_regression_pp"))
    if max_pp is None:
        max_pp = 3.0

    providers = baseline.get("providers") or {}
    if not isinstance(providers, dict):
        return False, [], ["baseline.providers must be an object"]

    latest_metrics = latest.get("metrics") or {}
    if not isinstance(latest_metrics, dict):
        return False, [], ["latest.metrics must be an object"]

    latest_provider = str(latest.get("provider") or "openai")
    checks: list[dict[str, Any]] = []
    summary: list[str] = [
        "## Extraction quality regression gate",
        "",
        f"- max_regression_pp: {max_pp}",
        f"- latest_provider: {latest_provider}",
        f"- latest_enforcement: {latest.get('enforcement')}",
        "",
        "### Provider enforcement map",
    ]

    for name, block in providers.items():
        if not isinstance(block, dict):
            continue
        enforcement = str(block.get("enforcement") or "manual")
        refreshed = block.get("last_refreshed")
        summary.append(
            f"- {name}: enforcement={enforcement}, last_refreshed={refreshed}, "
            f"source={block.get('source')}"
        )

    summary.append("")
    summary.append("### Checks (CI-enforced only)")

    ok = True
    for name, block in providers.items():
        if not isinstance(block, dict):
            continue
        if str(block.get("enforcement") or "") != "ci":
            continue
        if name != latest_provider:
            # Gate the CI provider that matches the latest report (OpenAI cassette run).
            continue
        base_metrics = block.get("metrics") or {}
        if not isinstance(base_metrics, dict):
            ok = False
            checks.append(
                {
                    "name": f"{name} metrics object",
                    "value": 0.0,
                    "limit": 0.0,
                    "ok": False,
                }
            )
            continue
        for metric_name, base_raw in base_metrics.items():
            base_val = _parse_float(base_raw)
            cur_val = _parse_float(latest_metrics.get(metric_name))
            if base_val is None or cur_val is None:
                passed = False
                drop = 0.0
            else:
                drop = _pp_drop(cur_val, base_val)
                passed = drop <= max_pp
            checks.append(
                {
                    "name": f"{name}.{metric_name} regression (pp)",
                    "value": drop,
                    "limit": max_pp,
                    "ok": passed,
                    "current": cur_val,
                    "baseline": base_val,
                }
            )
            mark = "PASS" if passed else "FAIL"
            summary.append(
                f"- {mark}: {name}.{metric_name} "
                f"(current={cur_val}, baseline={base_val}, drop_pp={drop:.3f}, limit={max_pp})"
            )
            ok = ok and passed

    if not any(c for c in checks):
        ok = False
        summary.append("- FAIL: no CI-enforced checks ran (provider mismatch or empty baseline)")

    return ok, checks, summary


def main() -> int:
    latest = json.loads(LATEST_PATH.read_text(encoding="utf-8"))
    baseline = json.loads(BASELINE_PATH.read_text(encoding="utf-8"))
    ok, checks, summary = evaluate_gate(latest, baseline)
    GATE_RESULT_PATH.parent.mkdir(parents=True, exist_ok=True)
    result = {
        "status": "pass" if ok else "fail",
        "checks": checks,
        "summary_lines": summary,
    }
    GATE_RESULT_PATH.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    print("\n".join(summary))
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
