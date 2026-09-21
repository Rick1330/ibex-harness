"""Unit tests for beat schedule registration."""

from __future__ import annotations

from datetime import timedelta

from app.celery_app import create_celery_app
from app.config import Settings
from app.task_names import (
    TASK_BUDGET_SPENT_ROLLUP,
    TASK_MAINTENANCE_NOOP_SWEEP,
    TASK_RECONCILE_USAGE_ACTUALS,
)


def test_beat_schedule_registered() -> None:
    settings = Settings(
        broker_url="redis://localhost:6379/1",
        result_backend="redis://localhost:6379/3",
        maintenance_beat_seconds=120.0,
        env="development",
    )
    app = create_celery_app(settings)
    schedule = app.conf.beat_schedule or {}
    assert "maintenance-noop-sweep" in schedule
    assert "reconcile-usage-actuals" in schedule
    assert "budget-spent-rollup" in schedule
    entry = schedule["maintenance-noop-sweep"]
    assert entry["task"] == TASK_MAINTENANCE_NOOP_SWEEP
    assert entry["options"]["queue"] == "maintenance"
    assert entry["schedule"].run_every == timedelta(seconds=120)
    assert schedule["reconcile-usage-actuals"]["task"] == TASK_RECONCILE_USAGE_ACTUALS
    assert schedule["budget-spent-rollup"]["task"] == TASK_BUDGET_SPENT_ROLLUP
