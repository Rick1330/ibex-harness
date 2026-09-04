"""Base Celery Task with shared retry policy and OTel span wrapping."""

from __future__ import annotations

from typing import Any

from celery import Task

from app.observability import run_task_in_span


class IbexTask(Task):
    """Shared task base — retry policy uses Celery built-ins (no custom backoff).

    Lifecycle logging is attached via ``app.task_lifecycle`` signal handlers.
    OTel spans and dead-letter handling are in ``app.observability``.
    """

    autoretry_for: tuple[type[BaseException], ...] = ()
    retry_backoff = True
    retry_backoff_max = 600
    retry_jitter = True
    max_retries = 3
    acks_late = True
    reject_on_worker_lost = True

    def __call__(self, *args: Any, **kwargs: Any) -> Any:
        task_id = self.request.id if self.request else None

        def _execute() -> Any:
            return super(IbexTask, self).__call__(*args, **kwargs)

        return run_task_in_span(self.name, task_id, kwargs, _execute)
