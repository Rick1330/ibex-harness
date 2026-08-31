"""Integration test helpers."""

from __future__ import annotations

import time

from celery import Celery
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


def wait_for_task_total(
    celery_app: Celery,
    task_name: str,
    minimum: int,
    timeout: float = 10.0,
) -> None:
    """Wait until worker stats show at least *minimum* runs of *task_name*."""
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        stats = celery_app.control.inspect(timeout=1.0).stats()
        if stats:
            total = sum(node.get("total", {}).get(task_name, 0) for node in stats.values())
            if total >= minimum:
                return
        time.sleep(0.05)
    msg = f"task {task_name!r} did not reach {minimum} runs within {timeout}s"
    raise TimeoutError(msg)


def worker_task_total(celery_app: Celery, task_name: str) -> int:
    """Return cumulative worker stats total for *task_name* (0 when unknown)."""
    stats = celery_app.control.inspect(timeout=1.0).stats()
    if not stats:
        return 0
    return sum(node.get("total", {}).get(task_name, 0) for node in stats.values())
