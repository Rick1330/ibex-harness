"""Unit tests for noop task callables."""

from __future__ import annotations

import app.tasks  # noqa: F401 — register tasks on module celery_app
from app.celery_app import celery_app
from app.task_names import (
    TASK_EMBEDDING_NOOP,
    TASK_EXTRACTION_NOOP,
    TASK_MAINTENANCE_NOOP_SWEEP,
    TASK_MCP_AUDIT_NOOP,
    TASK_RESULT_PROBE,
)
from app.tasks import maintenance, stubs


def test_stub_tasks_return_payloads() -> None:
    assert stubs.extraction_noop.run() == {"status": "noop", "queue": "extraction"}
    assert stubs.embedding_noop.run() == {"status": "noop", "queue": "embedding"}
    assert stubs.mcp_audit_noop.run() == {"status": "noop", "queue": "mcp_audit"}
    assert stubs.result_probe.run() == {"status": "probe", "queue": "maintenance"}


def test_maintenance_noop_sweep_returns_payload() -> None:
    assert maintenance.noop_sweep.run() == {"status": "noop"}


def test_registered_tasks_bind_expected_queues() -> None:
    """Decorator queue= must match milestone topology (not import-only smoke)."""
    expected = {
        TASK_EXTRACTION_NOOP: "extraction",
        TASK_EMBEDDING_NOOP: "embedding",
        TASK_MCP_AUDIT_NOOP: "mcp_audit",
        TASK_MAINTENANCE_NOOP_SWEEP: "maintenance",
        TASK_RESULT_PROBE: "maintenance",
    }
    for task_name, queue in expected.items():
        task = celery_app.tasks[task_name]
        assert task.queue == queue, f"{task_name} queue mismatch"
