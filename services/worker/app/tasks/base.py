"""Base Celery Task with shared retry and logging policy."""

from __future__ import annotations

import logging
import time
from typing import Any

from celery import Task

logger = logging.getLogger(__name__)


class IbexTask(Task):
    """Shared task base — retry policy uses Celery built-ins (no custom backoff).

    Milestone 3.5.A.2 attaches ``task_failure`` / OTel via global signals and
    ``@traced_task`` decorators; do not override ``on_failure`` here.
    """

    autoretry_for: tuple[type[BaseException], ...] = ()
    retry_backoff = True
    retry_backoff_max = 600
    retry_jitter = True
    max_retries = 3
    acks_late = True
    reject_on_worker_lost = True

    _start_monotonic: float | None = None

    def before_start(self, task_id: str, args: tuple[Any, ...], kwargs: dict[str, Any]) -> None:
        self._start_monotonic = time.monotonic()
        extra: dict[str, Any] = {
            "task_name": self.name,
            "task_id": task_id,
        }
        if org_id := kwargs.get("org_id"):
            extra["org_id"] = str(org_id)
        if agent_id := kwargs.get("agent_id"):
            extra["agent_id"] = str(agent_id)
        logger.info("task_start", extra=extra)

    def after_return(
        self,
        status: str,
        retval: Any,
        task_id: str,
        args: tuple[Any, ...],
        kwargs: dict[str, Any],
        einfo: Any,
    ) -> None:
        duration_ms: int | None = None
        if self._start_monotonic is not None:
            duration_ms = int((time.monotonic() - self._start_monotonic) * 1000)
        extra: dict[str, Any] = {
            "task_name": self.name,
            "task_id": task_id,
            "duration_ms": duration_ms,
        }
        if org_id := kwargs.get("org_id"):
            extra["org_id"] = str(org_id)
        if agent_id := kwargs.get("agent_id"):
            extra["agent_id"] = str(agent_id)
        if status == "FAILURE":
            logger.error("task_failure", extra=extra)
        else:
            logger.info("task_complete", extra=extra)
