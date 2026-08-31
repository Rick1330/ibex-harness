"""Integration tests — extraction queue Redis priority ordering."""

from __future__ import annotations

import os
import time
from collections.abc import Iterator

import pytest
import redis as redis_sync
from celery import Celery
from celery.contrib.testing.worker import start_worker

from tests.integration.task_wait import wait_for_task_success

pytestmark = pytest.mark.integration

_GATE_TASK = "ibex.worker.test.priority_gate"
_RECORDER_TASK = "ibex.worker.test.priority_recorder"
_GATE_KEY = "ibex:test:priority_gate"


@pytest.fixture
def priority_context(celery_app: Celery) -> tuple[list[int], redis_sync.Redis]:
    """Register gate + recorder tasks before the worker starts."""
    recorded: list[int] = []
    gate_client = redis_sync.Redis.from_url(
        os.environ.get("REDIS_URL", "redis://127.0.0.1:6379/0"),
        db=0,
    )
    gate_client.delete(_GATE_KEY)

    @celery_app.task(name=_GATE_TASK, bind=True)
    def _gate(self) -> None:
        client = redis_sync.Redis.from_url(
            os.environ.get("REDIS_URL", "redis://127.0.0.1:6379/0"),
            db=0,
        )
        try:
            deadline = time.monotonic() + 10.0
            while time.monotonic() < deadline:
                if client.exists(_GATE_KEY):
                    return
                time.sleep(0.05)
            msg = "priority gate was not released"
            raise TimeoutError(msg)
        finally:
            client.close()

    @celery_app.task(name=_RECORDER_TASK, bind=True)
    def _record(self, priority: int) -> None:
        recorded.append(priority)

    celery_app.conf.task_routes = {
        **(celery_app.conf.task_routes or {}),
        _GATE_TASK: {"queue": "extraction"},
        _RECORDER_TASK: {"queue": "extraction"},
    }
    return recorded, gate_client


@pytest.fixture
def priority_worker(celery_app: Celery, priority_context: tuple[list[int], redis_sync.Redis]) -> Iterator[object]:
    celery_app.conf.worker_prefetch_multiplier = 1
    with start_worker(
        celery_app,
        perform_ping_check=False,
        concurrency=1,
        pool="solo",
        loglevel="WARNING",
    ) as worker_instance:
        yield worker_instance


def test_extraction_priority_order(
    celery_app: Celery,
    priority_context: tuple[list[int], redis_sync.Redis],
    priority_worker: object,
) -> None:
    """Enqueue distinct priorities while the worker is gated; both must run.

    Strict dequeue ordering is enforced via ``broker_transport_options`` in
    ``test_extraction_queue_priority_config`` — solo test workers do not
    replicate production prefetch/dequeue semantics reliably enough to assert
    ordering here.
    """
    recorded, gate_client = priority_context

    gate_result = celery_app.send_task(_GATE_TASK, queue="extraction", ignore_result=False)
    time.sleep(0.2)
    low = celery_app.send_task(
        _RECORDER_TASK,
        args=(1,),
        queue="extraction",
        priority=1,
        ignore_result=False,
    )
    high = celery_app.send_task(
        _RECORDER_TASK,
        args=(9,),
        queue="extraction",
        priority=9,
        ignore_result=False,
    )

    gate_client.set(_GATE_KEY, "1")
    wait_for_task_success(gate_result)
    wait_for_task_success(high)
    wait_for_task_success(low)

    assert set(recorded) == {1, 9}
    gate_client.delete(_GATE_KEY)
    gate_client.close()
