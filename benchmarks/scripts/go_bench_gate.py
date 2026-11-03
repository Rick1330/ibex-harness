#!/usr/bin/env python3
"""Blocking relative regression gate for the proxy warm-path Go benchmarks.

The gate compares PR-head medians against a fresh benchmark run from the base
branch (normally ``main``) executed on the same runner, so host speed and CI
noise do not become part of the policy. It deliberately measures means
(``ns/op``), not p99; the scheduled full-chat k6 profile remains the p99 SLO
evidence path.
"""

from __future__ import annotations

import argparse
import json
import math
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

from go_bench_parser import BenchSample, GateInputError, parse_benchmark_line
from go_bench_results import (
    METRICS,
    BenchSummary,
    load_samples,
    pct_change,
    summarize,
)

__all__ = (
    "BenchSample",
    "BenchSummary",
    "Check",
    "GateInputError",
    "build_checks",
    "format_summary",
    "load_samples",
    "main",
    "parse_args",
    "parse_benchmark_line",
    "pct_change",
    "summarize",
    "write_result",
)

DEFAULT_BENCHMARKS = ("BenchmarkProxyOverhead", "BenchmarkProxyChatOverhead")
DEFAULT_TOLERANCE_PCT = 20.0


@dataclass(frozen=True)
class Check:
    benchmark: str
    metric: str
    base: float
    head: float
    change_pct: float
    passed: bool


def build_checks(
    base: dict[str, BenchSummary],
    head: dict[str, BenchSummary],
    benchmarks: Iterable[str],
    tolerance_pct: float,
) -> list[Check]:
    checks: list[Check] = []
    for name in benchmarks:
        if name not in base:
            raise GateInputError(f"base output is missing {name}")
        if name not in head:
            raise GateInputError(f"head output is missing {name}")
        for metric in METRICS:
            base_value = float(getattr(base[name], metric))
            head_value = float(getattr(head[name], metric))
            change = pct_change(head_value, base_value)
            checks.append(
                Check(
                    benchmark=name,
                    metric=metric,
                    base=base_value,
                    head=head_value,
                    change_pct=change,
                    passed=change <= tolerance_pct,
                )
            )
    return checks


def format_summary(
    checks: list[Check],
    *,
    base_ref: str,
    tolerance_pct: float,
) -> str:
    lines = [
        "## Go benchmark regression gate",
        "",
        f"- Base: `{base_ref}` (same-runner fresh run)",
        f"- Tolerance: `{tolerance_pct:g}%`",
        "- Scope: warm-path means; scheduled full-chat k6 remains the p99 SLO evidence.",
        "",
        "| Benchmark | Metric | Base | Head | Change | Result |",
        "| --- | --- | ---: | ---: | ---: | --- |",
    ]
    for check in checks:
        change = "inf" if math.isinf(check.change_pct) else f"{check.change_pct:+.1f}%"
        result = "PASS" if check.passed else "FAIL"
        lines.append(
            f"| `{check.benchmark}` | `{check.metric}` | {check.base:.2f} | "
            f"{check.head:.2f} | {change} | {result} |"
        )
    return "\n".join(lines) + "\n"


def write_result(
    path: Path,
    checks: list[Check],
    *,
    base_ref: str,
    tolerance_pct: float,
) -> None:
    payload = {
        "status": "pass" if all(check.passed for check in checks) else "fail",
        "base_ref": base_ref,
        "tolerance_pct": tolerance_pct,
        "scope": "warm_path_means_not_p99",
        "checks": [
            {
                "benchmark": check.benchmark,
                "metric": check.metric,
                "base": check.base,
                "head": check.head,
                "change_pct": None if math.isinf(check.change_pct) else check.change_pct,
                "ok": check.passed,
            }
            for check in checks
        ],
    }
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        # This path is an operator-supplied CLI argument, not network input;
        # the gate runs only in local/CI tooling.
        path.write_text(  # NOSONAR pythonsecurity:S2083,pythonsecurity:S8707  # nosemgrep
            json.dumps(payload, indent=2) + "\n",
            encoding="utf-8",
        )
    except OSError as exc:
        raise GateInputError(f"cannot write gate result {path}: {exc}") from exc


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base", required=True, type=Path, help="base-branch go test output")
    parser.add_argument("--head", required=True, type=Path, help="PR-head go test output")
    parser.add_argument("--base-ref", default="origin/main", help="auditable base reference")
    parser.add_argument(
        "--tolerance-pct",
        type=float,
        default=DEFAULT_TOLERANCE_PCT,
        help="maximum allowed regression percentage (default: 20)",
    )
    parser.add_argument("--output", type=Path, help="write gate result JSON here")
    parser.add_argument(
        "--benchmark",
        action="append",
        dest="benchmarks",
        help="benchmark name to compare (repeatable)",
    )
    args = parser.parse_args(argv)
    if not math.isfinite(args.tolerance_pct) or args.tolerance_pct < 0:
        parser.error("--tolerance-pct must be a non-negative finite number")
    if not args.benchmarks:
        args.benchmarks = list(DEFAULT_BENCHMARKS)
    return args


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    try:
        base = {name: summarize(rows) for name, rows in load_samples(args.base).items()}
        head = {name: summarize(rows) for name, rows in load_samples(args.head).items()}
        checks = build_checks(base, head, args.benchmarks, args.tolerance_pct)
        summary = format_summary(
            checks,
            base_ref=args.base_ref,
            tolerance_pct=args.tolerance_pct,
        )
        if args.output is not None:
            write_result(
                args.output,
                checks,
                base_ref=args.base_ref,
                tolerance_pct=args.tolerance_pct,
            )
    except GateInputError as exc:
        print(f"benchmark gate input error: {exc}", file=sys.stderr)
        return 2

    print(summary, end="")
    return 0 if all(check.passed for check in checks) else 1


if __name__ == "__main__":
    sys.exit(main())
