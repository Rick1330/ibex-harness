#!/usr/bin/env python3
"""Line parsing for ``go test -bench`` output."""

from __future__ import annotations

import math
import re
from dataclasses import dataclass

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
