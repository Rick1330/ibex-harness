"""Integration tests — dead-letter persistence after retry exhaustion."""

from __future__ import annotations

import asyncio
import time

import pytest
from celery import Celery
from celery.result import AsyncResult
from sqlalchemy import text

from app.config import Settings
from app.db import create_engine, create_session_factory, session_as_service_account
from app.observability import (
    dead_letter_persist_failed_total_for_task,
    dead_letter_total_for_task,
)
from app.task_names import TASK_MAINTENANCE_ALWAYS_FAIL

pytestmark = pytest.mark.integration


def _wait_for_failure(result: AsyncResult, timeout: float = 30.0) -> None:
    deadline = time.monotonic() + timeout
    while not result.ready():
        if time.monotonic() > deadline:
            msg = f"task {result.id!r} did not complete within {timeout}s"
            raise TimeoutError(msg)
        time.sleep(0.05)
    assert result.failed(), f"expected FAILURE, got {result.state!r}: {result.result!r}"


async def _fetch_failed_task_row(settings: Settings, task_id: str) -> tuple[str, int, str | None]:
    engine = create_engine(settings)
    try:
        factory = create_session_factory(engine)
        async with session_as_service_account(factory) as session:
            row = (
                await session.execute(
                    text(  # nosemgrep: python.sqlalchemy.security.audit.avoid-sqlalchemy-text.avoid-sqlalchemy-text
                        """
                        SELECT task_name, retry_count, left(traceback, 80) AS traceback_prefix
                        FROM ibex_core.failed_tasks
                        WHERE task_id = :task_id
                        """
                    ),
                    {"task_id": task_id},
                )
            ).one()
        return row.task_name, row.retry_count, row.traceback_prefix
    finally:
        await engine.dispose()


@pytest.mark.usefixtures("truncate_failed_tasks")
def test_dead_letter_persisted_after_retries_exhausted(
    eager_celery_app: Celery,
    integration_settings: Settings,
) -> None:
    baseline = dead_letter_total_for_task(TASK_MAINTENANCE_ALWAYS_FAIL)
    task = eager_celery_app.tasks[TASK_MAINTENANCE_ALWAYS_FAIL]
    result: AsyncResult = task.apply_async()
    _wait_for_failure(result, timeout=5.0)
    assert dead_letter_total_for_task(TASK_MAINTENANCE_ALWAYS_FAIL) == baseline + 1

    task_name, retry_count, traceback_prefix = asyncio.run(
        _fetch_failed_task_row(integration_settings, result.id)
    )
    assert task_name == TASK_MAINTENANCE_ALWAYS_FAIL
    assert retry_count == 3
    assert traceback_prefix == "[redacted]"


@pytest.mark.usefixtures("truncate_failed_tasks")
def test_dead_letter_counter_increments_when_db_unavailable(
    eager_celery_app: Celery,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from sqlalchemy.exc import SQLAlchemyError

    baseline = dead_letter_persist_failed_total_for_task(TASK_MAINTENANCE_ALWAYS_FAIL)

    def _raise_db_error(*_args: object, **_kwargs: object) -> None:
        raise SQLAlchemyError("simulated db outage")

    monkeypatch.setattr("app.observability._persist_dead_letter", _raise_db_error)
    task = eager_celery_app.tasks[TASK_MAINTENANCE_ALWAYS_FAIL]
    result: AsyncResult = task.apply_async()
    _wait_for_failure(result, timeout=5.0)
    assert (
        dead_letter_persist_failed_total_for_task(TASK_MAINTENANCE_ALWAYS_FAIL)
        == baseline + 1
    )
