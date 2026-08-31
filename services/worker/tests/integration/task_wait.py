"""Integration test helpers."""

from __future__ import annotations

import time

from celery.result import AsyncResult


def wait_for_task_success(result: AsyncResult, timeout: float = 10.0) -> None:
    """Poll until the task reaches a terminal state (works with ignore_result=True)."""
    deadline = time.monotonic() + timeout
    while not result.ready():
        if time.monotonic() > deadline:
            msg = f"task {result.id!r} did not complete within {timeout}s"
            raise TimeoutError(msg)
        time.sleep(0.05)
    if not result.successful():
        msg = f"task {result.id!r} failed: {result.result!r}"
        raise AssertionError(msg)
