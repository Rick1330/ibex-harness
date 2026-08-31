"""Unit tests for Celery app factory and queue topology."""

from __future__ import annotations

from kombu import Exchange, Queue

from app.celery_app import (
    DEFAULT_QUEUE_NAME,
    EXTRACTION_MAX_PRIORITY,
    TASK_ROUTES,
    create_celery_app,
    route_for_task,
)
from app.config import Settings
from app.task_names import ALL_TASK_NAMES


def _test_settings() -> Settings:
    return Settings(
        broker_url="redis://localhost:6379/1",
        result_backend="redis://localhost:6379/3",
        env="development",
    )


def test_celery_app_queues() -> None:
    app = create_celery_app(_test_settings())
    queues = app.conf.task_queues
    assert queues is not None
    names = {q.name for q in queues}
    assert names == {"extraction", "embedding", "maintenance", "mcp_audit"}
    assert DEFAULT_QUEUE_NAME not in names
    assert app.conf.task_default_queue == "maintenance"
    assert app.conf.task_create_missing_queues is False
    for q in queues:
        assert isinstance(q, Queue)
        assert isinstance(q.exchange, Exchange)
        assert q.routing_key == q.name
        assert q.exchange.name == q.name
        assert not q.queue_arguments
        if q.name == "extraction":
            assert q.max_priority == EXTRACTION_MAX_PRIORITY - 1
        else:
            assert q.max_priority is None


def test_extraction_queue_priority_config() -> None:
    app = create_celery_app(_test_settings())
    assert app.conf.task_queue_max_priority == EXTRACTION_MAX_PRIORITY
    transport = app.conf.broker_transport_options or {}
    assert transport.get("priority_steps") == list(range(EXTRACTION_MAX_PRIORITY))
    assert transport.get("queue_order_strategy") == "priority"


def test_task_routes_cover_all_task_names() -> None:
    for name in ALL_TASK_NAMES:
        assert name in TASK_ROUTES
        assert TASK_ROUTES[name]["queue"] != DEFAULT_QUEUE_NAME


def test_task_routes_no_default_queue() -> None:
    app = create_celery_app(_test_settings())
    for name in ALL_TASK_NAMES:
        queue = route_for_task(app, name)
        assert queue != DEFAULT_QUEUE_NAME


def test_result_policy_defaults() -> None:
    app = create_celery_app(_test_settings())
    assert app.conf.task_ignore_result is True
    assert app.conf.result_expires == 3600
    assert app.conf.worker_concurrency == 4
