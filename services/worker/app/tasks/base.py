"""Base Celery Task with shared retry policy."""

from __future__ import annotations

from celery import Task


class IbexTask(Task):
    """Shared task base — retry policy uses Celery built-ins (no custom backoff).

    Lifecycle logging is attached via ``app.task_lifecycle`` signal handlers.
    Milestone 3.5.A.2 adds ``task_failure`` / OTel via ``app.observability``;
    do not override ``on_failure`` here.
    """

    autoretry_for: tuple[type[BaseException], ...] = ()
    retry_backoff = True
    retry_backoff_max = 600
    retry_jitter = True
    max_retries = 3
    acks_late = True
    reject_on_worker_lost = True
