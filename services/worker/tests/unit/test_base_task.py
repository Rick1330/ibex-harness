"""Unit tests for IbexTask retry policy."""

from __future__ import annotations

from app.tasks.base import IbexTask


def test_ibex_task_retry_policy() -> None:
    task = IbexTask()
    assert task.retry_backoff is True
    assert task.retry_backoff_max == 600
    assert task.retry_jitter is True
    assert task.max_retries == 3
    assert task.acks_late is True
    assert task.reject_on_worker_lost is True
    assert task.autoretry_for == ()
