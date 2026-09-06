"""Prove open-loop load scheduling keeps multiple RPCs in flight."""

from __future__ import annotations

import argparse
import asyncio
import sys
import time
from pathlib import Path

import pytest

_ROOT = Path(__file__).resolve().parents[3]
_HARNESS = _ROOT / "benchmarks" / "context"
if str(_HARNESS) not in sys.path:
    sys.path.insert(0, str(_HARNESS))

from assemble_load import _drive_open_loop, _LoadPlan, _parse_error_rate


@pytest.mark.parametrize("raw", ("0", "0.0", "0.5", "1", "1.0"))
def test_parse_error_rate_accepts_unit_interval(raw: str) -> None:
    assert _parse_error_rate(raw) == float(raw)


@pytest.mark.parametrize("raw", ("-0.1", "1.01", "nan", "NaN", "inf", "-inf", "abc"))
def test_parse_error_rate_rejects_invalid(raw: str) -> None:
    with pytest.raises(argparse.ArgumentTypeError):
        _parse_error_rate(raw)


@pytest.mark.asyncio
async def test_open_loop_keeps_requests_in_flight() -> None:
    """When each call is slower than the launch interval, concurrency > 1."""
    in_flight = 0
    peak = 0
    lock = asyncio.Lock()

    async def slow_stub(_req: object, timeout: float = 1.0) -> object:
        del timeout
        nonlocal in_flight, peak
        async with lock:
            in_flight += 1
            peak = max(peak, in_flight)
        await asyncio.sleep(0.05)
        async with lock:
            in_flight -= 1
        return object()

    started = time.perf_counter()
    stats = await _drive_open_loop(
        slow_stub,
        object(),
        _LoadPlan(duration_s=0.12, target_rps=100),
    )
    elapsed = time.perf_counter() - started
    assert stats.latencies_ms
    assert stats.attempted == stats.succeeded
    assert peak >= 2
    # Open-loop should finish the window without serializing all sleeps.
    assert elapsed < 0.12 + 0.05 * len(stats.latencies_ms)
