"""Celery task lifecycle logging via signals (avoids IbexTask method overrides)."""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from typing import Any

from celery.signals import task_postrun, task_prerun

from app.task_context import task_context_from_kwargs

logger = logging.getLogger(__name__)

_start_times: dict[str, float] = {}


@dataclass
class TaskRunContext:
    """Mutable signal payload — keeps handler arity within CodeScene limits."""

    task_id: str | None = None
    task: Any = None
    kwargs: dict[str, Any] | None = None
    state: str | None = None
    extra: dict[str, str] = field(default_factory=dict)


def _log_task_start(ctx: TaskRunContext) -> None:
    if ctx.task_id is None or ctx.task is None:
        return
    _start_times[ctx.task_id] = time.monotonic()
    extra: dict[str, Any] = {
        "task_name": ctx.task.name,
        "task_id": ctx.task_id,
        **task_context_from_kwargs(ctx.kwargs),
    }
    logger.info("task_start", extra=extra)


def _log_task_complete(ctx: TaskRunContext) -> None:
    if ctx.task_id is None or ctx.task is None:
        return
    started = _start_times.pop(ctx.task_id, None)
    duration_ms: int | None = None
    if started is not None:
        duration_ms = int((time.monotonic() - started) * 1000)
    extra: dict[str, Any] = {
        "task_name": ctx.task.name,
        "task_id": ctx.task_id,
        "duration_ms": duration_ms,
        **task_context_from_kwargs(ctx.kwargs),
    }
    if ctx.state == "FAILURE":
        logger.error("task_failure", extra=extra)
    else:
        logger.info("task_complete", extra=extra)


@task_prerun.connect
def _on_task_prerun(**signal_kwargs: Any) -> None:
    _log_task_start(
        TaskRunContext(
            task_id=signal_kwargs.get("task_id"),
            task=signal_kwargs.get("task"),
            kwargs=signal_kwargs.get("kwargs"),
        )
    )


@task_postrun.connect
def _on_task_postrun(**signal_kwargs: Any) -> None:
    _log_task_complete(
        TaskRunContext(
            task_id=signal_kwargs.get("task_id"),
            task=signal_kwargs.get("task"),
            kwargs=signal_kwargs.get("kwargs"),
            state=signal_kwargs.get("state"),
        )
    )
