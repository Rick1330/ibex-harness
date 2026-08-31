"""Unit tests for task lifecycle signal logging."""

from __future__ import annotations

import logging
from types import SimpleNamespace

import pytest

from app import task_lifecycle


def test_log_task_start_emits_context(caplog: pytest.LogCaptureFixture) -> None:
    caplog.set_level(logging.INFO)
    task = SimpleNamespace(name="ibex.worker.test.sample")
    task_lifecycle._log_task_start(
        task_id="task-id-1",
        task=task,
        kwargs={"org_id": "org-1", "agent_id": "agent-1"},
    )
    assert any("task_start" in record.message for record in caplog.records)


def test_log_task_complete_failure(caplog: pytest.LogCaptureFixture) -> None:
    caplog.set_level(logging.INFO)
    task = SimpleNamespace(name="ibex.worker.test.sample")
    task_lifecycle._start_times["task-id-2"] = 0.0
    task_lifecycle._log_task_complete(
        task_id="task-id-2",
        task=task,
        kwargs={},
        state="FAILURE",
    )
    assert any(record.levelname == "ERROR" for record in caplog.records)


def test_log_task_complete_success_with_context(caplog: pytest.LogCaptureFixture) -> None:
    caplog.set_level(logging.INFO)
    task = SimpleNamespace(name="ibex.worker.test.sample")
    task_lifecycle._start_times["task-id-4"] = 0.0
    task_lifecycle._log_task_complete(
        task_id="task-id-4",
        task=task,
        kwargs={"org_id": "org-1", "agent_id": "agent-1"},
        state="SUCCESS",
    )
    assert any("task_complete" in record.message for record in caplog.records)


def test_log_task_complete_success(caplog: pytest.LogCaptureFixture) -> None:
    caplog.set_level(logging.INFO)
    task = SimpleNamespace(name="ibex.worker.test.sample")
    task_lifecycle._start_times["task-id-3"] = 0.0
    task_lifecycle._log_task_complete(
        task_id="task-id-3",
        task=task,
        kwargs={},
        state="SUCCESS",
    )
    assert any("task_complete" in record.message for record in caplog.records)
