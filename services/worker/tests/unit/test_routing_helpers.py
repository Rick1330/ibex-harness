"""Unit tests for celery routing helpers."""

from __future__ import annotations

import pytest

import app.tasks  # noqa: F401
from app.celery_app import create_celery_app, registered_task_names, route_for_task
from app.config import Settings


def _settings() -> Settings:
    return Settings(
        broker_url="redis://localhost:6379/1",
        result_backend="redis://localhost:6379/3",
        env="development",
    )


def test_registered_task_names_lists_ibex_tasks() -> None:
    celery = create_celery_app(_settings())
    names = registered_task_names(celery)
    assert names
    assert all(name.startswith("ibex.worker.") for name in names)


def test_route_for_task_missing_raises() -> None:
    celery = create_celery_app(_settings())
    with pytest.raises(KeyError, match="no route"):
        route_for_task(celery, "ibex.worker.unknown.task")


def test_route_for_task_missing_queue_raises() -> None:
    celery = create_celery_app(_settings())
    celery.conf.task_routes = {"ibex.worker.bad.route": {}}
    with pytest.raises(KeyError, match="missing queue"):
        route_for_task(celery, "ibex.worker.bad.route")
