#!/usr/bin/env python3
"""Loading and aggregation for ``go test -bench`` output."""

from __future__ import annotations

import math
import statistics
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

from go_bench_parser import BenchSample, GateInputError, parse_benchmark_line

METRICS = ("ns_per_op", "bytes_per_op", "allocs_per_op")


@dataclass(frozen=True)
class BenchSummary:
    samples: int
    ns_per_op: float
    bytes_per_op: float
    allocs_per_op: float


def _read_output(path: Path) -> str:
    if not path.is_file():
        raise GateInputError(f"benchmark output not found: {path}")
    try:
        # This path is an operator-supplied CLI argument, not network input;
        # the script has no request or LLM input surface.
        return path.read_text(  # NOSONAR pythonsecurity:S2083,pythonsecurity:S8707  # nosemgrep
            encoding="utf-8"
        )
    except OSError as exc:
        raise GateInputError(f"cannot read benchmark output {path}: {exc}") from exc


def _index_samples(text: str, path: Path) -> dict[str, list[BenchSample]]:
    by_name: dict[str, list[BenchSample]] = {}
    for line in text.splitlines():
        sample = parse_benchmark_line(line)
        if sample is not None:
            by_name.setdefault(sample.name, []).append(sample)
    if not by_name:
        raise GateInputError(f"no benchmark samples found in {path}")
    return by_name


def load_samples(path: Path) -> dict[str, list[BenchSample]]:
    return _index_samples(_read_output(path), path)


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
    if math.isclose(base, 0.0, abs_tol=1e-12):
        return 0.0 if math.isclose(head, 0.0, abs_tol=1e-12) else float("inf")
    return ((head - base) / base) * 100.0
