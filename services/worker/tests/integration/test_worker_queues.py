"""Integration tests — worker startup and per-queue consumption."""

from __future__ import annotations

import pytest
from celery import Celery
from celery.result import AsyncResult

from app.task_names import (
    TASK_EMBEDDING_NOOP,
    TASK_EXTRACTION_NOOP,
    TASK_MAINTENANCE_NOOP_SWEEP,
    TASK_MCP_AUDIT_NOOP,
)

pytestmark = pytest.mark.integration


@pytest.mark.parametrize(
    ("task_name", "queue"),
    [
        (TASK_EXTRACTION_NOOP, "extraction"),
        (TASK_EMBEDDING_NOOP, "embedding"),
        (TASK_MAINTENANCE_NOOP_SWEEP, "maintenance"),
        (TASK_MCP_AUDIT_NOOP, "mcp_audit"),
    ],
)
def test_noop_consumed_per_queue(
    celery_app: Celery,
    worker: object,
    task_name: str,
    queue: str,
) -> None:
    result: AsyncResult = celery_app.send_task(task_name, queue=queue)
    payload = result.get(timeout=10)
    assert payload is not None
    if task_name == TASK_MAINTENANCE_NOOP_SWEEP:
        assert payload["status"] == "noop"
    else:
        assert payload["status"] == "noop"
        assert payload["queue"] == queue


def test_worker_starts_and_pings(celery_app: Celery, worker: object) -> None:
    replies = celery_app.control.ping(timeout=5.0)
    assert replies
    assert any("ok" in node.get("ok", "").lower() for reply in replies for node in reply.values())
