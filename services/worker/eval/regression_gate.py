#!/usr/bin/env python3
"""Regression gate for extraction quality eval (absolute percentage points)."""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

from gate_checks import (
    check_ci_block,
    is_matching_ci_block,
    parse_float,
    pp_drop,
    resolve_max_pp,
    within_max_pp,
)
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

# Compat aliases for tests.
_parse_float = parse_float
_pp_drop = pp_drop
_within_max_pp = within_max_pp


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


def _invalid_max_pp_result() -> tuple[bool, list[dict[str, Any]], list[str]]:
    return (
        False,
        [],
        [
            "## Extraction quality regression gate",
            "",
            "- FAIL: policy.max_regression_pp must be a finite number",
        ],
    )


def _header(max_pp: float, latest: dict[str, Any], providers: dict[str, Any]) -> list[str]:
    return [
        "## Extraction quality regression gate",
        "",
        f"- max_regression_pp: {max_pp}",
        f"- latest_provider: {latest.get('provider') or 'openai'}",
        f"- latest_enforcement: {latest.get('enforcement')}",
        "",
        *_provider_summary_lines(providers),
        "",
        "### Checks (CI-enforced only)",
    ]


def _run_ci_checks(
    providers: dict[str, Any],
    latest_provider: str,
    latest_metrics: dict[str, Any],
    max_pp: float,
) -> tuple[bool, list[dict[str, Any]], list[str]]:
    ok = True
    checks: list[dict[str, Any]] = []
    summary: list[str] = []
    for name, block in providers.items():
        if not is_matching_ci_block(name, block, latest_provider):
            continue
        assert isinstance(block, dict)
        block_ok, block_checks, block_lines = check_ci_block(
            name, block, latest_metrics, max_pp
        )
        checks.extend(block_checks)
        summary.extend(block_lines)
        ok = ok and block_ok
    return ok, checks, summary


def evaluate_gate(
    latest: dict[str, Any],
    baseline: dict[str, Any],
) -> tuple[bool, list[dict[str, Any]], list[str]]:
    policy = baseline.get("policy") or {}
    max_pp = resolve_max_pp(policy if isinstance(policy, dict) else {})
    if max_pp is None:
        return _invalid_max_pp_result()

    providers = baseline.get("providers") or {}
    if not isinstance(providers, dict):
        return False, [], ["baseline.providers must be an object"]

    latest_metrics = latest.get("metrics") or {}
    if not isinstance(latest_metrics, dict):
        return False, [], ["latest.metrics must be an object"]

    latest_provider = str(latest.get("provider") or "openai")
    summary = _header(max_pp, latest, providers)
    ok, checks, check_lines = _run_ci_checks(
        providers, latest_provider, latest_metrics, max_pp
    )
    summary.extend(check_lines)
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
