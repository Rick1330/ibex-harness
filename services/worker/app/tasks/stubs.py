"""No-op tasks for queue routing and integration-test harness (m3.5.A.1)."""

from __future__ import annotations

from typing import Any

from app.celery_app import celery_app
from app.task_names import (
    TASK_EMBEDDING_NOOP,
    TASK_EXTRACTION_NOOP,
    TASK_MCP_AUDIT_NOOP,
    TASK_RESULT_PROBE,
)
from app.tasks.base import IbexTask


@celery_app.task(
    bind=True,
    base=IbexTask,
    name=TASK_EXTRACTION_NOOP,
    queue="extraction",
)
def extraction_noop(self: IbexTask, **kwargs: Any) -> dict[str, str]:
    """Skeleton extraction queue consumer."""
    return {"status": "noop", "queue": "extraction"}


@celery_app.task(
    bind=True,
    base=IbexTask,
    name=TASK_EMBEDDING_NOOP,
    queue="embedding",
)
def embedding_noop(self: IbexTask, **kwargs: Any) -> dict[str, str]:
    """Skeleton embedding queue consumer."""
    return {"status": "noop", "queue": "embedding"}


@celery_app.task(
    bind=True,
    base=IbexTask,
    name=TASK_MCP_AUDIT_NOOP,
    queue="mcp_audit",
)
def mcp_audit_noop(self: IbexTask, **kwargs: Any) -> dict[str, str]:
    """Skeleton MCP audit queue consumer."""
    return {"status": "noop", "queue": "mcp_audit"}


@celery_app.task(
    bind=True,
    base=IbexTask,
    name=TASK_RESULT_PROBE,
    queue="maintenance",
    ignore_result=False,
)
def result_probe(self: IbexTask, **kwargs: Any) -> dict[str, str]:
    """Opt-in result tracking for integration tests (ignore_result=False)."""
    return {"status": "probe", "queue": "maintenance"}
