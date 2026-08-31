"""Celery task lifecycle logging via signals (avoids IbexTask method overrides)."""

from __future__ import annotations

import logging
import time
from typing import Any

from celery.signals import task_postrun, task_prerun

logger = logging.getLogger(__name__)

_start_times: dict[str, float] = {}


def _context_from_kwargs(kwargs: dict[str, Any] | None) -> dict[str, str]:
    extra: dict[str, str] = {}
    if kwargs is None:
        return extra
    if org_id := kwargs.get("org_id"):
        extra["org_id"] = str(org_id)
    if agent_id := kwargs.get("agent_id"):
        extra["agent_id"] = str(agent_id)
    return extra


@task_prerun.connect
def _log_task_start(
    task_id: str | None = None,
    task: Any = None,
    kwargs: dict[str, Any] | None = None,
    **_: Any,
) -> None:
    if task_id is None or task is None:
        return
    _start_times[task_id] = time.monotonic()
    extra: dict[str, Any] = {
        "task_name": task.name,
        "task_id": task_id,
        **_context_from_kwargs(kwargs),
    }
    logger.info("task_start", extra=extra)


@task_postrun.connect
def _log_task_complete(
    task_id: str | None = None,
    task: Any = None,
    kwargs: dict[str, Any] | None = None,
    state: str | None = None,
    **_: Any,
) -> None:
    if task_id is None or task is None:
        return
    started = _start_times.pop(task_id, None)
    duration_ms: int | None = None
    if started is not None:
        duration_ms = int((time.monotonic() - started) * 1000)
    extra: dict[str, Any] = {
        "task_name": task.name,
        "task_id": task_id,
        "duration_ms": duration_ms,
        **_context_from_kwargs(kwargs),
    }
    if state == "FAILURE":
        logger.error("task_failure", extra=extra)
    else:
        logger.info("task_complete", extra=extra)
