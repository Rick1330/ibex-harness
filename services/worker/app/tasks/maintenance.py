"""Maintenance beat tasks: dead-letter probes and the retention sweep."""

from __future__ import annotations

import asyncio
import logging
from typing import Any

from app.celery_app import celery_app
from app.config import get_settings
from app.retention import (
    ClickHouseUsageFactsPartitions,
    NoopUsageFactsPartitions,
    RetentionPolicy,
    SqlAlchemyRetentionStore,
    UsageFactsPartitions,
    run_retention_sweep,
)
from app.task_names import (
    TASK_MAINTENANCE_ALWAYS_FAIL,
    TASK_MAINTENANCE_NOOP_SWEEP,
    TASK_MAINTENANCE_RETENTION_SWEEP,
)
from app.tasks.base import IbexTask

logger = logging.getLogger(__name__)


class ForcedFailureError(RuntimeError):
    """Intentional failure for dead-letter integration tests."""


@celery_app.task(
    bind=True,
    base=IbexTask,
    name=TASK_MAINTENANCE_NOOP_SWEEP,
    queue="maintenance",
    soft_time_limit=300,
    time_limit=600,
)
def noop_sweep(self: IbexTask, **kwargs: Any) -> dict[str, str]:
    """Scheduled maintenance placeholder — attach real sweep logic in later milestones."""
    return {"status": "noop"}


@celery_app.task(
    bind=True,
    base=IbexTask,
    name=TASK_MAINTENANCE_ALWAYS_FAIL,
    queue="maintenance",
    soft_time_limit=300,
    time_limit=600,
    autoretry_for=(ForcedFailureError,),
    max_retries=3,
    retry_backoff=False,
    retry_jitter=False,
    default_retry_delay=0,
)
def always_fail(self: IbexTask, **kwargs: Any) -> None:
    """Always raises — used by integration tests to exercise dead-letter handling."""
    raise ForcedFailureError("forced failure for dead-letter test")


def _usage_facts_partitions(dsn: str | None) -> UsageFactsPartitions:
    """Partition source for the ClickHouse window, or a no-op when it is unset."""
    if not dsn:
        logger.warning("retention_sweep: no clickhouse dsn; usage_facts window skipped")
        return NoopUsageFactsPartitions()
    return ClickHouseUsageFactsPartitions(dsn)


@celery_app.task(
    bind=True,
    base=IbexTask,
    name=TASK_MAINTENANCE_RETENTION_SWEEP,
    queue="maintenance",
    soft_time_limit=300,
    time_limit=600,
    autoretry_for=(OSError,),
    retry_backoff=True,
    retry_jitter=True,
    max_retries=5,
)
def retention_sweep(self: IbexTask, **kwargs: Any) -> dict[str, Any]:
    """Apply the failed-task, idempotency, and usage-facts retention windows.

    Postgres runs first and independently of ClickHouse: a dead-letter row is
    the higher-risk store, and an unreachable ClickHouse must not postpone it.
    """
    del self, kwargs
    settings = get_settings()
    db_url = getattr(settings, "database_url", None)
    if not db_url:
        logger.info("retention_sweep skipped: missing database url")
        return {"status": "skipped", "reason": "missing_dsn"}
    store = SqlAlchemyRetentionStore(db_url)
    partitions = _usage_facts_partitions(getattr(settings, "clickhouse_dsn", None))
    try:
        report = asyncio.run(
            run_retention_sweep(
                store=store,
                partitions=partitions,
                policy=RetentionPolicy.from_settings(settings),
            )
        )
    finally:
        asyncio.run(store.aclose())
    logger.info(
        "retention_sweep done scrubbed=%d deleted_tasks=%d deleted_ledger=%d dropped=%s",
        report.scrubbed,
        report.deleted_tasks,
        report.deleted_ledger,
        ",".join(report.dropped_months) or "-",
    )
    return {"status": "ok", **report.as_dict()}
