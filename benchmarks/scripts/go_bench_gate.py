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
import statistics
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

DEFAULT_BENCHMARKS = ("BenchmarkProxyOverhead", "BenchmarkProxyChatOverhead")
DEFAULT_TOLERANCE_PCT = 20.0
METRICS = ("ns_per_op", "bytes_per_op", "allocs_per_op")


@dataclass(frozen=True)
class BenchSample:
    name: str
    ns_per_op: float
    bytes_per_op: float
    allocs_per_op: float


@dataclass(frozen=True)
class BenchSummary:
    samples: int
    ns_per_op: float
    bytes_per_op: float
    allocs_per_op: float


@dataclass(frozen=True)
class Check:
    benchmark: str
    metric: str
    base: float
    head: float
    change_pct: float
    passed: bool


class GateInputError(ValueError):
    """Benchmark output was missing or malformed."""


def parse_benchmark_line(line: str) -> BenchSample | None:
    """Parse one ``go test -bench`` sample line.

    Accepts names with a ``-GOMAXPROCS`` suffix and ignores non-benchmark lines.
    """
    fields = line.split()
    if len(fields) < 4 or not fields[0].startswith("Benchmark"):
        return None
    name = fields[0].split("-", 1)[0]
    try:
        ns_per_op = float(fields[2])
    except ValueError:
        return None
    if ns_per_op <= 0:
        return None
    return BenchSample(
        name=name,
        ns_per_op=ns_per_op,
        bytes_per_op=_read_metric(fields, "B/op"),
        allocs_per_op=_read_metric(fields, "allocs/op"),
    )


def _read_metric(fields: list[str], unit: str) -> float:
    for index, field in enumerate(fields):
        if field != unit or index == 0:
            continue
        try:
            return float(fields[index - 1])
        except ValueError:
            return 0.0
    return 0.0


def load_samples(path: Path) -> dict[str, list[BenchSample]]:
    if not path.is_file():
        raise GateInputError(f"benchmark output not found: {path}")
    by_name: dict[str, list[BenchSample]] = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        sample = parse_benchmark_line(line)
        if sample is not None:
            by_name.setdefault(sample.name, []).append(sample)
    if not by_name:
        raise GateInputError(f"no benchmark samples found in {path}")
    return by_name


def summarize(samples: Iterable[BenchSample]) -> BenchSummary:
    rows = list(samples)
    if not rows:
        raise GateInputError("cannot summarize an empty sample set")
    return BenchSummary(
        samples=len(rows),
        ns_per_op=statistics.median(row.ns_per_op for row in rows),
        bytes_per_op=statistics.median(row.bytes_per_op for row in rows),
        allocs_per_op=statistics.median(row.allocs_per_op for row in rows),
    )


def pct_change(head: float, base: float) -> float:
    if base == 0.0:
        return 0.0 if head == 0.0 else float("inf")
    return ((head - base) / base) * 100.0


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
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")


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
    if args.tolerance_pct < 0:
        parser.error("--tolerance-pct must be non-negative")
    if not args.benchmarks:
        args.benchmarks = list(DEFAULT_BENCHMARKS)
    return args


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    try:
        base = {name: summarize(rows) for name, rows in load_samples(args.base).items()}
        head = {name: summarize(rows) for name, rows in load_samples(args.head).items()}
        checks = build_checks(base, head, args.benchmarks, args.tolerance_pct)
    except GateInputError as exc:
        print(f"benchmark gate input error: {exc}", file=sys.stderr)
        return 2

    summary = format_summary(checks, base_ref=args.base_ref, tolerance_pct=args.tolerance_pct)
    print(summary, end="")
    if args.output is not None:
        write_result(
            args.output,
            checks,
            base_ref=args.base_ref,
            tolerance_pct=args.tolerance_pct,
        )
    return 0 if all(check.passed for check in checks) else 1


if __name__ == "__main__":
    sys.exit(main())
