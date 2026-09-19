"""Unit tests for 4.P.5 worker soft/hard time limits (F4-020 residual)."""

from __future__ import annotations

import pytest
from celery.exceptions import TimeLimitExceeded

from app.celery_app import celery_app
from app.tasks.base import IbexTask
from app.tasks.billing_reconcile import budget_spent_rollup, reconcile_usage_actuals
from app.tasks.maintenance import always_fail, noop_sweep


def test_budget_spent_rollup_time_limits() -> None:
    assert budget_spent_rollup.soft_time_limit == 60
    assert budget_spent_rollup.time_limit == 120


def test_reconcile_usage_actuals_time_limits() -> None:
    assert reconcile_usage_actuals.soft_time_limit == 300
    assert reconcile_usage_actuals.time_limit == 600


def test_maintenance_task_time_limits() -> None:
    assert noop_sweep.soft_time_limit == 300
    assert noop_sweep.time_limit == 600
    assert always_fail.soft_time_limit == 300
    assert always_fail.time_limit == 600


def test_hard_time_limit_exceeded_is_not_swallowed() -> None:
    """TimeLimitExceeded must propagate through IbexTask (not silently caught)."""

    @celery_app.task(
        bind=True,
        base=IbexTask,
        name="tests.unit.forced_time_limit",
        soft_time_limit=1,
        time_limit=2,
    )
    def forced_limit(self: IbexTask) -> None:
        del self
        raise TimeLimitExceeded()

    with pytest.raises(TimeLimitExceeded):
        forced_limit()
