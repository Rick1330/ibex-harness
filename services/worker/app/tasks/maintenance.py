"""Maintenance beat tasks (skeleton — real sweeps land in later milestones)."""

from __future__ import annotations

from typing import Any

from app.celery_app import celery_app
from app.task_names import TASK_MAINTENANCE_NOOP_SWEEP
from app.tasks.base import IbexTask


@celery_app.task(
    bind=True,
    base=IbexTask,
    name=TASK_MAINTENANCE_NOOP_SWEEP,
    queue="maintenance",
)
def noop_sweep(self: IbexTask, **kwargs: Any) -> dict[str, str]:
    """Scheduled maintenance placeholder — attach real sweep logic in A.2+."""
    return {"status": "noop"}
