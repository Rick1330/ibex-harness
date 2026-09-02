"""Maintenance beat tasks (skeleton — real sweeps land in later milestones)."""

from __future__ import annotations

from typing import Any

from app.celery_app import celery_app
from app.task_names import TASK_MAINTENANCE_ALWAYS_FAIL, TASK_MAINTENANCE_NOOP_SWEEP
from app.tasks.base import IbexTask


class ForcedFailureError(RuntimeError):
    """Intentional failure for dead-letter integration tests."""


@celery_app.task(
    bind=True,
    base=IbexTask,
    name=TASK_MAINTENANCE_NOOP_SWEEP,
    queue="maintenance",
)
def noop_sweep(self: IbexTask, **kwargs: Any) -> dict[str, str]:
    """Scheduled maintenance placeholder — attach real sweep logic in later milestones."""
    return {"status": "noop"}


@celery_app.task(
    bind=True,
    base=IbexTask,
    name=TASK_MAINTENANCE_ALWAYS_FAIL,
    queue="maintenance",
    autoretry_for=(ForcedFailureError,),
    max_retries=3,
    retry_backoff=False,
    retry_jitter=False,
    default_retry_delay=0,
)
def always_fail(self: IbexTask, **kwargs: Any) -> None:
    """Always raises — used by integration tests to exercise dead-letter handling."""
    raise ForcedFailureError("forced failure for dead-letter test")
