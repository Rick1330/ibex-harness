"""Observability hooks for Celery tasks (OTel, dead-letter, Prometheus)."""

from __future__ import annotations

import asyncio
import logging
import traceback
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any, TypeVar

import asyncpg
from celery.exceptions import Retry
from celery.signals import task_failure, worker_process_init, worker_ready
from opentelemetry.trace import Status, StatusCode
from prometheus_client import Counter, Gauge, start_http_server
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from app.config import Settings, get_settings
from app.db import create_engine, create_session_factory
from app.repositories.failed_tasks import FailedTaskRecord, insert_failed_task
from app.task_context import (
    parse_org_id,
    redact_exception_message,
    redact_traceback_for_persistence,
    sanitize_kwargs_for_persistence,
    task_context_from_kwargs,
)
from app.telemetry import TRACER_NAME, get_tracer, init_tracing

logger = logging.getLogger(__name__)

F = TypeVar("F", bound=Callable[..., Any])

PROCESS_UP = Gauge(
    "ibex_process_up",
    "1 when the worker process is serving metrics",
)
DEAD_LETTER_COUNTER = Counter(
    "ibex_worker_task_dead_letter_total",
    "Celery tasks dead-lettered after retries exhausted",
    ["task_name"],
)

_engine: AsyncEngine | None = None
_session_factory: async_sessionmaker[AsyncSession] | None = None
_metrics_started = False

__all__ = [
    "DEAD_LETTER_COUNTER",
    "PROCESS_UP",
    "dead_letter_total_for_task",
    "on_task_failure",
    "reset_observability_for_tests",
    "run_task_in_span",
    "traced_task",
]


def traced_task(name: str) -> Callable[[F], F]:
    """Decorator wrapping a callable in an OTel span (used by IbexTask.__call__)."""

    def decorator(fn: F) -> F:
        def wrapper(*args: Any, **kwargs: Any) -> Any:
            return run_task_in_span(name, None, kwargs or {}, lambda: fn(*args, **kwargs))

        wrapper.__name__ = getattr(fn, "__name__", name)
        wrapper.__doc__ = fn.__doc__
        return wrapper  # type: ignore[return-value]

    return decorator


def run_task_in_span(
    name: str,
    task_id: str | None,
    task_kwargs: dict[str, Any],
    fn: Callable[[], Any],
) -> Any:
    """Execute *fn* inside a span tagged with safe task metadata."""
    tracer = get_tracer()
    with tracer.start_as_current_span(
        name,
        set_status_on_exception=False,
        record_exception=False,
    ) as span:
        span.set_attribute("worker.task", name)
        if task_id:
            span.set_attribute("celery.task_id", task_id)
        for key, value in task_context_from_kwargs(task_kwargs).items():
            span.set_attribute(f"ibex.{key}", value)
        try:
            return fn()
        except Retry:
            raise
        except BaseException as exc:
            span.record_exception(exc)
            span.set_status(Status(StatusCode.ERROR, type(exc).__name__))
            raise


def dead_letter_total_for_task(task_name: str) -> float:
    """Return current counter value for tests."""
    return DEAD_LETTER_COUNTER.labels(task_name=task_name)._value.get()  # type: ignore[attr-defined]


def reset_observability_for_tests() -> None:
    """Test-only reset of module globals (DB pool, metrics server flag)."""
    global _engine, _session_factory, _metrics_started
    _engine = None
    _session_factory = None
    _metrics_started = False


def _should_dead_letter(sender: Any) -> bool:
    request = getattr(sender, "request", None)
    if request is None:
        return True
    retries = getattr(request, "retries", 0)
    max_retries = getattr(sender, "max_retries", 0)
    return retries >= max_retries


def _format_traceback(einfo: Any, exc: BaseException | None) -> str:
    if einfo is not None and getattr(einfo, "traceback", None):
        return str(einfo.traceback)
    if exc is not None:
        return "".join(traceback.format_exception(type(exc), exc, exc.__traceback__))
    return ""


@dataclass(frozen=True, slots=True)
class DeadLetterPayload:
    """Sanitized dead-letter fields collected from a Celery task_failure signal."""

    task_name: str
    task_id: str
    kwargs: dict[str, Any]
    exception: BaseException | None
    traceback_text: str
    retry_count: int


@dataclass(frozen=True, slots=True)
class TaskFailureContext:
    """Celery task_failure signal payload."""

    sender: Any
    task_id: str | None
    exception: BaseException | None
    kwargs: dict[str, Any] | None
    einfo: Any

    @classmethod
    def from_signal(cls, signal_kwargs: dict[str, Any]) -> TaskFailureContext:
        return cls(
            sender=signal_kwargs.get("sender"),
            task_id=signal_kwargs.get("task_id"),
            exception=signal_kwargs.get("exception"),
            kwargs=signal_kwargs.get("kwargs"),
            einfo=signal_kwargs.get("einfo"),
        )


def _persist_dead_letter(settings: Settings, payload: DeadLetterPayload) -> None:
    if not settings.database_url or _session_factory is None:
        logger.error(
            "dead_letter_skipped_no_database",
            extra={"task_name": payload.task_name, "task_id": payload.task_id},
        )
        return

    org_id = parse_org_id(payload.kwargs)
    exc = payload.exception or RuntimeError("unknown task failure")
    asyncio.run(
        insert_failed_task(
            _session_factory,
            FailedTaskRecord(
                task_name=payload.task_name,
                task_id=payload.task_id,
                args=(),
                kwargs=sanitize_kwargs_for_persistence(payload.kwargs),
                exception_type=type(exc).__name__,
                exception_message=redact_exception_message(exc),
                traceback_text=redact_traceback_for_persistence(payload.traceback_text),
                retry_count=payload.retry_count,
                org_id=org_id,
            ),
        )
    )


def _handle_task_failure(ctx: TaskFailureContext) -> None:
    if ctx.sender is None or ctx.task_id is None:
        return
    if not _should_dead_letter(ctx.sender):
        return

    task_name = getattr(ctx.sender, "name", "unknown")
    DEAD_LETTER_COUNTER.labels(task_name=task_name).inc()

    request = getattr(ctx.sender, "request", None)
    retry_count = int(getattr(request, "retries", 0)) if request is not None else 0
    task_kwargs = ctx.kwargs if ctx.kwargs is not None else {}
    payload = DeadLetterPayload(
        task_name=task_name,
        task_id=ctx.task_id,
        kwargs=task_kwargs,
        exception=ctx.exception,
        traceback_text=_format_traceback(ctx.einfo, ctx.exception),
        retry_count=retry_count,
    )

    settings = get_settings()
    try:
        _persist_dead_letter(settings, payload)
    except (SQLAlchemyError, asyncpg.PostgresError, OSError, RuntimeError):
        logger.exception(
            "dead_letter_persist_failed",
            extra={
                "task_name": task_name,
                "task_id": ctx.task_id,
                **task_context_from_kwargs(task_kwargs),
            },
        )


@task_failure.connect
def on_task_failure(**signal_kwargs: Any) -> None:
    """Dead-letter handler — fires once per exhausted-retry failure."""
    _handle_task_failure(TaskFailureContext.from_signal(signal_kwargs))


def _start_metrics_server(port: int) -> None:
    global _metrics_started
    if _metrics_started:
        return
    start_http_server(port)
    PROCESS_UP.set(1)
    _metrics_started = True


def _init_database(settings: Settings) -> None:
    global _engine, _session_factory
    if not settings.database_url:
        return
    if _session_factory is not None:
        return
    _engine = create_engine(settings)
    _session_factory = create_session_factory(_engine)


@worker_process_init.connect
def _on_worker_process_init(**signal_kwargs: Any) -> None:
    del signal_kwargs
    init_tracing()
    _init_database(get_settings())


@worker_ready.connect
def _on_worker_ready(**signal_kwargs: Any) -> None:
    del signal_kwargs
    settings = get_settings()
    _start_metrics_server(settings.metrics_port)
    logger.info(
        "worker_observability_ready",
        extra={
            "metrics_port": settings.metrics_port,
            "database_configured": bool(settings.database_url),
            "tracer": TRACER_NAME,
        },
    )
