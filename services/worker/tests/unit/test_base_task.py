"""Unit tests for IbexTask retry policy."""

from __future__ import annotations

from unittest.mock import PropertyMock, patch

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


def test_ibex_task_call_wraps_run_task_in_span() -> None:
    task = IbexTask()
    task.name = "ibex.worker.test"
    request = type("Req", (), {"id": "task-123"})()

    with (
        patch.object(type(task), "request", new_callable=PropertyMock, return_value=request),
        patch("app.tasks.base.run_task_in_span", return_value="ok") as run_span,
    ):
        result = task.__call__(kw="val")

    assert result == "ok"
    run_span.assert_called_once()
    args = run_span.call_args[0]
    assert args[0] == "ibex.worker.test"
    assert args[1] == "task-123"
    assert args[2] == {"kw": "val"}
