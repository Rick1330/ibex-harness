"""Unit tests for IbexTask lifecycle logging."""

from __future__ import annotations

import logging

import pytest

from app.tasks.base import IbexTask


def test_ibex_task_before_start_logs_context(caplog: pytest.LogCaptureFixture) -> None:
    caplog.set_level(logging.INFO)
    task = IbexTask()
    task.name = "ibex.worker.test.sample"
    task.before_start(
        "task-id-1",
        (),
        {"org_id": "org-1", "agent_id": "agent-1"},
    )
    assert any("task_start" in record.message for record in caplog.records)


def test_ibex_task_after_return_logs_failure(caplog: pytest.LogCaptureFixture) -> None:
    caplog.set_level(logging.INFO)
    task = IbexTask()
    task.name = "ibex.worker.test.sample"
    task.before_start("task-id-2", (), {})
    task.after_return("FAILURE", None, "task-id-2", (), {}, None)
    assert any(record.levelname == "ERROR" for record in caplog.records)


def test_ibex_task_after_return_logs_success_with_context(caplog: pytest.LogCaptureFixture) -> None:
    caplog.set_level(logging.INFO)
    task = IbexTask()
    task.name = "ibex.worker.test.sample"
    task.before_start("task-id-4", (), {"org_id": "org-1", "agent_id": "agent-1"})
    task.after_return(
        "SUCCESS",
        {"ok": True},
        "task-id-4",
        (),
        {"org_id": "org-1", "agent_id": "agent-1"},
        None,
    )
    assert any("task_complete" in record.message for record in caplog.records)


def test_ibex_task_after_return_logs_success(caplog: pytest.LogCaptureFixture) -> None:
    caplog.set_level(logging.INFO)
    task = IbexTask()
    task.name = "ibex.worker.test.sample"
    task.before_start("task-id-3", (), {})
    task.after_return("SUCCESS", {"ok": True}, "task-id-3", (), {}, None)
    assert any("task_complete" in record.message for record in caplog.records)
