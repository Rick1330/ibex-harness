"""Unit tests for task_failure dead-letter handler."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import asyncpg
import pytest
from sqlalchemy.exc import SQLAlchemyError

from app.observability import (
    dead_letter_persist_failed_total_for_task,
    dead_letter_total_for_task,
    on_task_failure,
)
from app.task_names import TASK_MAINTENANCE_ALWAYS_FAIL


class _FakeRequest:
    def __init__(self, retries: int) -> None:
        self.retries = retries


class _FakeSender:
    def __init__(self, *, retries: int, max_retries: int = 3) -> None:
        self.name = TASK_MAINTENANCE_ALWAYS_FAIL
        self.max_retries = max_retries
        self.request = _FakeRequest(retries)


def test_task_failure_skips_when_retries_remaining() -> None:
    baseline = dead_letter_total_for_task(TASK_MAINTENANCE_ALWAYS_FAIL)
    on_task_failure(
        sender=_FakeSender(retries=0),
        task_id="t-retry",
        exception=RuntimeError("transient"),
        args=(),
        kwargs={},
    )
    assert dead_letter_total_for_task(TASK_MAINTENANCE_ALWAYS_FAIL) == baseline


def test_task_failure_increments_counter_when_retries_exhausted() -> None:
    baseline = dead_letter_total_for_task(TASK_MAINTENANCE_ALWAYS_FAIL)
    with patch("app.observability._persist_dead_letter", return_value=True) as persist:
        on_task_failure(
            sender=_FakeSender(retries=3),
            task_id="t-final",
            exception=RuntimeError("final"),
            args=("a",),
            kwargs={"org_id": "550e8400-e29b-41d4-a716-446655440000"},
            einfo=SimpleNamespace(traceback="traceback text"),
        )
    assert dead_letter_total_for_task(TASK_MAINTENANCE_ALWAYS_FAIL) == baseline + 1
    persist.assert_called_once()


def test_task_failure_skips_counter_for_duplicate_delivery() -> None:
    baseline = dead_letter_total_for_task(TASK_MAINTENANCE_ALWAYS_FAIL)
    with patch("app.observability._persist_dead_letter", return_value=False):
        on_task_failure(
            sender=_FakeSender(retries=3),
            task_id="t-dup",
            exception=RuntimeError("final"),
            args=(),
            kwargs={},
        )
    assert dead_letter_total_for_task(TASK_MAINTENANCE_ALWAYS_FAIL) == baseline


def test_task_failure_persist_failed_counter_on_db_error() -> None:
    dead_letter_baseline = dead_letter_total_for_task(TASK_MAINTENANCE_ALWAYS_FAIL)
    persist_failed_baseline = dead_letter_persist_failed_total_for_task(
        TASK_MAINTENANCE_ALWAYS_FAIL
    )
    with patch(
        "app.observability._persist_dead_letter",
        side_effect=SQLAlchemyError("db down"),
    ):
        on_task_failure(
            sender=_FakeSender(retries=3),
            task_id="t-db-fail",
            exception=RuntimeError("final"),
            args=(),
            kwargs={},
        )
    assert dead_letter_total_for_task(TASK_MAINTENANCE_ALWAYS_FAIL) == dead_letter_baseline
    assert (
        dead_letter_persist_failed_total_for_task(TASK_MAINTENANCE_ALWAYS_FAIL)
        == persist_failed_baseline + 1
    )


def test_task_failure_logs_db_error_without_suppressing(caplog: pytest.LogCaptureFixture) -> None:
    persist_failed_baseline = dead_letter_persist_failed_total_for_task(
        TASK_MAINTENANCE_ALWAYS_FAIL
    )
    with patch(
        "app.observability._persist_dead_letter",
        side_effect=asyncpg.PostgresError("connection refused"),
    ):
        on_task_failure(
            sender=_FakeSender(retries=3),
            task_id="t-pg",
            exception=RuntimeError("final"),
            args=(),
            kwargs={},
        )
    assert (
        dead_letter_persist_failed_total_for_task(TASK_MAINTENANCE_ALWAYS_FAIL)
        == persist_failed_baseline + 1
    )
    assert any(
        record.message == "dead_letter_persist_failed" for record in caplog.records
    )


def test_should_dead_letter_without_request() -> None:
    sender = MagicMock()
    sender.request = None
    sender.name = TASK_MAINTENANCE_ALWAYS_FAIL
    baseline = dead_letter_total_for_task(TASK_MAINTENANCE_ALWAYS_FAIL)
    with patch("app.observability._persist_dead_letter", return_value=True):
        on_task_failure(
            sender=sender,
            task_id="t-no-req",
            exception=RuntimeError("x"),
            args=(),
            kwargs={},
        )
    assert dead_letter_total_for_task(TASK_MAINTENANCE_ALWAYS_FAIL) == baseline + 1
