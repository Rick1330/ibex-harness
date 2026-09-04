"""CI metric check helpers for extraction regression gate."""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any

from metrics import gated_metric_names

_PP_TOLERANCE = 1e-9


def parse_float(value: object) -> float | None:
    if value is None:
        return None
    try:
        parsed = float(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return None
    if not math.isfinite(parsed):
        return None
    return parsed


def pp_drop(cur: float, base: float) -> float:
    return (base - cur) * 100.0


def within_max_pp(drop: float, max_pp: float) -> bool:
    return drop <= max_pp + _PP_TOLERANCE


def fail_check(name: str) -> dict[str, Any]:
    return {"name": name, "value": 0.0, "limit": 0.0, "ok": False}


@dataclass(frozen=True, slots=True)
class MetricCtx:
    provider_name: str
    base_metrics: dict[str, Any]
    latest_metrics: dict[str, Any]
    max_pp: float


def one_metric_check(ctx: MetricCtx, metric_name: str) -> tuple[bool, dict[str, Any], str]:
    if metric_name not in ctx.base_metrics:
        check = fail_check(f"{ctx.provider_name}.{metric_name} missing from baseline")
        line = f"- FAIL: {ctx.provider_name}.{metric_name} missing from baseline metrics"
        return False, check, line
    base_val = parse_float(ctx.base_metrics.get(metric_name))
    cur_val = parse_float(ctx.latest_metrics.get(metric_name))
    if base_val is None or cur_val is None:
        passed = False
        drop = 0.0
    else:
        drop = pp_drop(cur_val, base_val)
        passed = within_max_pp(drop, ctx.max_pp)
    check = {
        "name": f"{ctx.provider_name}.{metric_name} regression (pp)",
        "value": drop,
        "limit": ctx.max_pp,
        "ok": passed,
        "current": cur_val,
        "baseline": base_val,
    }
    mark = "PASS" if passed else "FAIL"
    line = (
        f"- {mark}: {ctx.provider_name}.{metric_name} "
        f"(current={cur_val}, baseline={base_val}, drop_pp={drop:.3f}, limit={ctx.max_pp})"
    )
    return passed, check, line


def ci_metric_checks(ctx: MetricCtx) -> tuple[bool, list[dict[str, Any]], list[str]]:
    checks: list[dict[str, Any]] = []
    summary: list[str] = []
    ok = True
    for metric_name in gated_metric_names():
        passed, check, line = one_metric_check(ctx, metric_name)
        checks.append(check)
        summary.append(line)
        ok = ok and passed
    return ok, checks, summary


def resolve_max_pp(policy: dict[str, Any]) -> float | None:
    if "max_regression_pp" not in policy or policy.get("max_regression_pp") is None:
        return 3.0
    return parse_float(policy.get("max_regression_pp"))


def is_matching_ci_block(name: str, block: object, latest_provider: str) -> bool:
    if not isinstance(block, dict):
        return False
    if str(block.get("enforcement") or "") != "ci":
        return False
    return name == latest_provider


def check_ci_block(
    name: str,
    block: dict[str, Any],
    latest_metrics: dict[str, Any],
    max_pp: float,
) -> tuple[bool, list[dict[str, Any]], list[str]]:
    base_metrics = block.get("metrics") or {}
    if not isinstance(base_metrics, dict):
        return False, [fail_check(f"{name} metrics object")], []
    ctx = MetricCtx(
        provider_name=name,
        base_metrics=base_metrics,
        latest_metrics=latest_metrics,
        max_pp=max_pp,
    )
    return ci_metric_checks(ctx)
