#!/usr/bin/env python3
"""Parsing and aggregation for ``go test -bench`` output."""

from __future__ import annotations

import math
import re
import statistics
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

METRICS = ("ns_per_op", "bytes_per_op", "allocs_per_op")
_BENCHMARK_LINE = re.compile(
    r"^(?P<name>Benchmark\S+?)(?:-\d+)?\s+\S+\s+"
    r"(?P<ns>[0-9.eE+-]+)\s+ns/op\s+"
    r"(?P<bytes>[0-9.eE+-]+)\s+B/op\s+"
    r"(?P<allocs>[0-9.eE+-]+)\s+allocs/op\s*$"
)


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


class GateInputError(ValueError):
    """Benchmark output was missing or malformed."""


def _parse_metric(raw: str, unit: str, line: str) -> float:
    try:
        value = float(raw)
    except ValueError as exc:
        raise GateInputError(f"invalid {unit} value in benchmark line: {line!r}") from exc
    if not math.isfinite(value) or value < 0:
        raise GateInputError(f"invalid {unit} value in benchmark line: {line!r}")
    return value


def parse_benchmark_line(line: str) -> BenchSample | None:
    """Parse one ``go test -bench`` sample line.

    Ignores non-benchmark output, but rejects malformed benchmark lines instead
    of silently treating missing allocation metrics as zero.
    """
    stripped = line.strip()
    if not stripped.startswith("Benchmark"):
        return None
    match = _BENCHMARK_LINE.match(stripped)
    if match is None:
        raise GateInputError(f"malformed benchmark line: {line!r}")
    return BenchSample(
        name=match["name"],
        ns_per_op=_parse_metric(match["ns"], "ns/op", stripped),
        bytes_per_op=_parse_metric(match["bytes"], "B/op", stripped),
        allocs_per_op=_parse_metric(match["allocs"], "allocs/op", stripped),
    )


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
