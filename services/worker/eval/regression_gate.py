#!/usr/bin/env python3
"""Regression gate for extraction quality eval (absolute percentage points).

CI-enforced provider blocks only (baseline providers.*.enforcement == \"ci\").
Fails the process (exit 1) when any gated metric drops by more than
policy.max_regression_pp absolute percentage points (default 3.0).

Manual/vLLM blocks are printed for side-by-side visibility but never fail CI.
"""

from __future__ import annotations

import json
import math
import sys
from pathlib import Path
from typing import Any

from metrics import gated_metric_names
from path_guard import (
    UnsafePathError,
    resolve_baseline_path,
    resolve_gate_result_path,
    resolve_latest_path,
)

_DIR = Path(__file__).resolve().parent
LATEST_PATH = _DIR / "output" / "latest.json"
BASELINE_PATH = _DIR / "gold_set" / "v1" / "baseline_results.json"
GATE_RESULT_PATH = _DIR / "output" / "gate-result.json"

_PP_TOLERANCE = 1e-9


def _parse_float(value: object) -> float | None:
    if value is None:
        return None
    try:
        parsed = float(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return None
    if not math.isfinite(parsed):
        return None
    return parsed


def _pp_drop(cur: float, base: float) -> float:
    """Absolute percentage-point drop (positive means regression for higher-is-better)."""
    return (base - cur) * 100.0


def _within_max_pp(drop: float, max_pp: float) -> bool:
    return drop <= max_pp + _PP_TOLERANCE


def _provider_summary_lines(providers: dict[str, Any]) -> list[str]:
    lines = ["### Provider enforcement map"]
    for name, block in providers.items():
        if not isinstance(block, dict):
            continue
        enforcement = str(block.get("enforcement") or "manual")
        refreshed = block.get("last_refreshed")
        lines.append(
            f"- {name}: enforcement={enforcement}, last_refreshed={refreshed}, "
            f"source={block.get('source')}"
        )
    return lines


def _fail_check(name: str) -> dict[str, Any]:
    return {"name": name, "value": 0.0, "limit": 0.0, "ok": False}


def _ci_metric_checks(
    *,
    provider_name: str,
    base_metrics: dict[str, Any],
    latest_metrics: dict[str, Any],
    max_pp: float,
) -> tuple[bool, list[dict[str, Any]], list[str]]:
    checks: list[dict[str, Any]] = []
    summary: list[str] = []
    ok = True
    required = gated_metric_names()
    for metric_name in required:
        if metric_name not in base_metrics:
            ok = False
            checks.append(_fail_check(f"{provider_name}.{metric_name} missing from baseline"))
            summary.append(
                f"- FAIL: {provider_name}.{metric_name} missing from baseline metrics"
            )
            continue
        base_val = _parse_float(base_metrics.get(metric_name))
        cur_val = _parse_float(latest_metrics.get(metric_name))
        if base_val is None or cur_val is None:
            passed = False
            drop = 0.0
        else:
            drop = _pp_drop(cur_val, base_val)
            passed = _within_max_pp(drop, max_pp)
        checks.append(
            {
                "name": f"{provider_name}.{metric_name} regression (pp)",
                "value": drop,
                "limit": max_pp,
                "ok": passed,
                "current": cur_val,
                "baseline": base_val,
            }
        )
        mark = "PASS" if passed else "FAIL"
        summary.append(
            f"- {mark}: {provider_name}.{metric_name} "
            f"(current={cur_val}, baseline={base_val}, drop_pp={drop:.3f}, limit={max_pp})"
        )
        ok = ok and passed
    return ok, checks, summary


def evaluate_gate(
    latest: dict[str, Any],
    baseline: dict[str, Any],
) -> tuple[bool, list[dict[str, Any]], list[str]]:
    policy = baseline.get("policy") or {}
    if "max_regression_pp" not in policy or policy.get("max_regression_pp") is None:
        max_pp = 3.0
    else:
        max_pp = _parse_float(policy.get("max_regression_pp"))
        if max_pp is None:
            return (
                False,
                [],
                [
                    "## Extraction quality regression gate",
                    "",
                    "- FAIL: policy.max_regression_pp must be a finite number",
                ],
            )

    providers = baseline.get("providers") or {}
    if not isinstance(providers, dict):
        return False, [], ["baseline.providers must be an object"]

    latest_metrics = latest.get("metrics") or {}
    if not isinstance(latest_metrics, dict):
        return False, [], ["latest.metrics must be an object"]

    latest_provider = str(latest.get("provider") or "openai")
    summary: list[str] = [
        "## Extraction quality regression gate",
        "",
        f"- max_regression_pp: {max_pp}",
        f"- latest_provider: {latest_provider}",
        f"- latest_enforcement: {latest.get('enforcement')}",
        "",
        *_provider_summary_lines(providers),
        "",
        "### Checks (CI-enforced only)",
    ]

    ok = True
    checks: list[dict[str, Any]] = []
    for name, block in providers.items():
        if not isinstance(block, dict):
            continue
        if str(block.get("enforcement") or "") != "ci":
            continue
        if name != latest_provider:
            continue
        base_metrics = block.get("metrics") or {}
        if not isinstance(base_metrics, dict):
            ok = False
            checks.append(_fail_check(f"{name} metrics object"))
            continue
        block_ok, block_checks, block_lines = _ci_metric_checks(
            provider_name=name,
            base_metrics=base_metrics,
            latest_metrics=latest_metrics,
            max_pp=max_pp,
        )
        checks.extend(block_checks)
        summary.extend(block_lines)
        ok = ok and block_ok

    if not checks:
        ok = False
        summary.append("- FAIL: no CI-enforced checks ran (provider mismatch or empty baseline)")

    return ok, checks, summary


def _load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))  # NOSONAR pythonsecurity:S2083


def main() -> int:
    try:
        latest_path = resolve_latest_path(LATEST_PATH)
        baseline_path = resolve_baseline_path(BASELINE_PATH)
        gate_path = resolve_gate_result_path(GATE_RESULT_PATH)
    except UnsafePathError as exc:
        print(str(exc), file=sys.stderr)
        return 1

    latest = _load_json(latest_path)
    baseline = _load_json(baseline_path)
    ok, checks, summary = evaluate_gate(latest, baseline)
    gate_path.parent.mkdir(parents=True, exist_ok=True)
    result = {
        "status": "pass" if ok else "fail",
        "checks": checks,
        "summary_lines": summary,
    }
    gate_path.write_text(  # NOSONAR pythonsecurity:S2083,pythonsecurity:S8707
        json.dumps(result, indent=2) + "\n",
        encoding="utf-8",
    )
    print("\n".join(summary))
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
