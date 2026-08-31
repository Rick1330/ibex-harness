"""Integration tests — extraction queue Redis priority ordering."""

from __future__ import annotations

import threading
import time
from collections.abc import Iterator

import pytest
from celery import Celery
from celery.contrib.testing.worker import start_worker

from tests.integration.task_wait import wait_for_task_success

pytestmark = pytest.mark.integration

_GATE_TASK = "ibex.worker.test.priority_gate"
_RECORDER_TASK = "ibex.worker.test.priority_recorder"


@pytest.fixture
def priority_context(celery_app: Celery) -> tuple[list[int], threading.Event]:
    """Register gate + recorder tasks before the worker starts."""
    recorded: list[int] = []
    gate = threading.Event()

    @celery_app.task(name=_GATE_TASK, bind=True)
    def _gate(self) -> None:
        gate.wait(timeout=5)

    @celery_app.task(name=_RECORDER_TASK, bind=True)
    def _record(self, priority: int) -> None:
        recorded.append(priority)

    celery_app.conf.task_routes = {
        **(celery_app.conf.task_routes or {}),
        _GATE_TASK: {"queue": "extraction"},
        _RECORDER_TASK: {"queue": "extraction"},
    }
    return recorded, gate


@pytest.fixture
def priority_worker(celery_app: Celery, priority_context: tuple[list[int], threading.Event]) -> Iterator[object]:
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
    priority_context: tuple[list[int], threading.Event],
    priority_worker: object,
) -> None:
    recorded, gate = priority_context

    gate_result = celery_app.send_task(_GATE_TASK, queue="extraction")
    time.sleep(0.2)
    low = celery_app.send_task(
        _RECORDER_TASK,
        args=(1,),
        queue="extraction",
        priority=1,
    )
    high = celery_app.send_task(
        _RECORDER_TASK,
        args=(9,),
        queue="extraction",
        priority=9,
    )

    gate.set()
    wait_for_task_success(gate_result)
    wait_for_task_success(high)
    wait_for_task_success(low)

    assert recorded.index(9) < recorded.index(1)
