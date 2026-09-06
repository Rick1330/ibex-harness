"""Prove open-loop load scheduling keeps multiple RPCs in flight."""

from __future__ import annotations

import asyncio
import sys
import time
from pathlib import Path

import pytest

_ROOT = Path(__file__).resolve().parents[3]
_HARNESS = _ROOT / "benchmarks" / "context"
if str(_HARNESS) not in sys.path:
    sys.path.insert(0, str(_HARNESS))

from assemble_load import _drive_open_loop, _LoadPlan


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
    samples = await _drive_open_loop(
        slow_stub,
        object(),
        _LoadPlan(duration_s=0.12, target_rps=100, record_errors=False),
    )
    elapsed = time.perf_counter() - started
    assert samples
    assert peak >= 2
    # Open-loop should finish the window without serializing all sleeps.
    assert elapsed < 0.12 + 0.05 * len(samples)
