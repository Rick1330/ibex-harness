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
from tests.integration.task_wait import wait_for_task_success

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
    result: AsyncResult = celery_app.send_task(
        task_name,
        queue=queue,
        ignore_result=False,
    )
    wait_for_task_success(result)
    payload = result.get(timeout=1)
    assert payload is not None
    if task_name == TASK_MAINTENANCE_NOOP_SWEEP:
        assert payload["status"] == "noop"
    else:
        assert payload["status"] == "noop"
        assert payload["queue"] == queue


def test_worker_starts_and_pings(celery_app: Celery, worker: object) -> None:
    replies = celery_app.control.ping(timeout=5.0)
    assert replies
    assert any(node.get("ok") == "pong" for reply in replies for node in reply.values())


def test_routed_task_without_explicit_queue_kwarg(
    celery_app: Celery,
    worker: object,
) -> None:
    """task_routes must deliver work without per-send queue= override."""
    result: AsyncResult = celery_app.send_task(
        TASK_EXTRACTION_NOOP,
        ignore_result=False,
    )
    wait_for_task_success(result)
    payload = result.get(timeout=1)
    assert payload == {"status": "noop", "queue": "extraction"}


def test_publish_to_stock_celery_queue_fails(celery_app: Celery, worker: object) -> None:
    """Negative: the stock ``celery`` queue is not declared — publish must fail closed."""
    with pytest.raises(KeyError, match="celery"):
        celery_app.send_task(
            TASK_EXTRACTION_NOOP,
            queue="celery",
            ignore_result=False,
        )
