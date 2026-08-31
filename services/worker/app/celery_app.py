"""Celery application factory, queue topology, and beat schedule."""

from __future__ import annotations

from celery import Celery
from celery.schedules import schedule
from kombu import Exchange, Queue

from app.config import Settings, get_settings, queue_names
from app.logging import configure_logging
from app.task_names import (
    TASK_EMBEDDING_NOOP,
    TASK_EXTRACTION_NOOP,
    TASK_MAINTENANCE_NOOP_SWEEP,
    TASK_MCP_AUDIT_NOOP,
    TASK_RESULT_PROBE,
)

EXTRACTION_MAX_PRIORITY = 10

TASK_ROUTES: dict[str, dict[str, str]] = {
    TASK_EXTRACTION_NOOP: {"queue": "extraction"},
    TASK_EMBEDDING_NOOP: {"queue": "embedding"},
    TASK_MCP_AUDIT_NOOP: {"queue": "mcp_audit"},
    TASK_MAINTENANCE_NOOP_SWEEP: {"queue": "maintenance"},
    TASK_RESULT_PROBE: {"queue": "maintenance"},
}

DEFAULT_QUEUE_NAME = "celery"


def _build_task_queues() -> tuple[Queue, ...]:
    queues: list[Queue] = []
    for name in queue_names():
        exchange = Exchange(name, type="direct")
        queues.append(Queue(name, exchange, routing_key=name))
    return tuple(queues)


def create_celery_app(settings: Settings | None = None) -> Celery:
    """Build a configured Celery app (broker, queues, routes, beat)."""
    configure_logging()
    cfg = settings or get_settings()

    celery = Celery("ibex_worker")
    celery.conf.update(
        broker_url=cfg.resolved_broker_url,
        result_backend=cfg.resolved_result_backend,
        task_serializer="json",
        result_serializer="json",
        accept_content=["json"],
        task_ignore_result=True,
        result_expires=cfg.result_expires_seconds,
        task_acks_late=True,
        task_reject_on_worker_lost=True,
        worker_concurrency=cfg.worker_concurrency,
        worker_prefetch_multiplier=cfg.worker_prefetch_multiplier,
        worker_max_tasks_per_child=cfg.worker_max_tasks_per_child,
        worker_hostname=cfg.worker_hostname,
        task_queues=_build_task_queues(),
        task_routes=TASK_ROUTES,
        task_create_missing_queues=False,
        broker_transport_options={
            "priority_steps": list(range(EXTRACTION_MAX_PRIORITY)),
            "queue_order_strategy": "priority",
        },
        task_queue_max_priority=EXTRACTION_MAX_PRIORITY,
        beat_schedule={
            "maintenance-noop-sweep": {
                "task": TASK_MAINTENANCE_NOOP_SWEEP,
                "schedule": schedule(run_every=cfg.maintenance_beat_seconds),
                "options": {"queue": "maintenance"},
            },
        },
        imports=("app.tasks",),
    )
    celery.set_default()
    return celery


def registered_task_names(celery_app: Celery) -> tuple[str, ...]:
    """Return sorted registered task names (excluding Celery builtins)."""
    return tuple(sorted(name for name in celery_app.tasks if name.startswith("ibex.worker.")))


def route_for_task(celery_app: Celery, task_name: str) -> str:
    """Resolve the queue a task name routes to (raises if unmapped)."""
    routes = celery_app.conf.task_routes or {}
    entry = routes.get(task_name)
    if entry is None:
        msg = f"no route for task {task_name!r}"
        raise KeyError(msg)
    queue = entry.get("queue")
    if not queue:
        msg = f"route for {task_name!r} missing queue"
        raise KeyError(msg)
    return str(queue)


celery_app = create_celery_app()

# Register task modules (decorators bind to celery_app above).
import app.task_lifecycle  # noqa: F401
import app.tasks  # noqa: F401
