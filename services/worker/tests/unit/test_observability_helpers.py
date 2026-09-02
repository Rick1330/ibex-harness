"""Unit tests for observability helpers and worker_ready."""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.config import Settings
from app.observability import (
    DeadLetterPayload,
    _format_traceback,
    _on_worker_process_init,
    _on_worker_ready,
    _persist_dead_letter,
    _should_dead_letter,
    reset_observability_for_tests,
)


class _FakeRequest:
    def __init__(self, retries: int) -> None:
        self.retries = retries


class _FakeSender:
    def __init__(self, *, retries: int, max_retries: int = 3) -> None:
        self.request = _FakeRequest(retries)
        self.max_retries = max_retries


def test_should_dead_letter_retry_guard() -> None:
    assert _should_dead_letter(_FakeSender(retries=0)) is False
    assert _should_dead_letter(_FakeSender(retries=2)) is False
    assert _should_dead_letter(_FakeSender(retries=3)) is True


def test_should_dead_letter_without_request() -> None:
    sender = MagicMock()
    sender.request = None
    assert _should_dead_letter(sender) is True


def test_format_traceback_prefers_einfo() -> None:
    einfo = SimpleNamespace(traceback="from-einfo")
    assert _format_traceback(einfo, ValueError("x")) == "from-einfo"


def test_format_traceback_from_exception() -> None:
    try:
        raise ValueError("boom")
    except ValueError as exc:
        text = _format_traceback(None, exc)
    assert "ValueError" in text
    assert "boom" in text


def test_persist_dead_letter_skips_without_database() -> None:
    settings = Settings(database_url=None)
    _persist_dead_letter(
        settings,
        DeadLetterPayload(
            task_name="t",
            task_id="id",
            kwargs={},
            exception=RuntimeError("x"),
            traceback_text="tb",
            retry_count=0,
        ),
    )


def test_persist_dead_letter_persists_with_database(monkeypatch: pytest.MonkeyPatch) -> None:
    settings = Settings(database_url="postgresql://u:p@localhost/ibex?sslmode=disable")
    monkeypatch.setattr("app.observability._session_factory", MagicMock())
    insert_mock = AsyncMock(return_value=True)
    monkeypatch.setattr("app.observability.insert_failed_task", insert_mock)

    org_id = "550e8400-e29b-41d4-a716-446655440000"
    _persist_dead_letter(
        settings,
        DeadLetterPayload(
            task_name="t",
            task_id="id",
            kwargs={
                "org_id": org_id,
                "memory_content": "must not persist",
            },
            exception=RuntimeError("secret-token-abc"),
            traceback_text="Traceback with secrets",
            retry_count=3,
        ),
    )

    insert_mock.assert_awaited_once()
    record = insert_mock.await_args.args[1]
    assert record.task_name == "t"
    assert record.task_id == "id"
    assert record.args == ()
    assert record.kwargs == {"org_id": org_id}
    assert record.exception_type == "RuntimeError"
    assert record.exception_message == "[redacted]"
    assert record.traceback_text == "[redacted]"
    assert record.retry_count == 3


def test_start_metrics_server_multiprocess(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    from app.observability import _start_metrics_server, reset_observability_for_tests

    reset_observability_for_tests()
    monkeypatch.setenv("PROMETHEUS_MULTIPROC_DIR", str(tmp_path))
    start_http_server_mock = MagicMock()
    collector_mock = MagicMock()
    monkeypatch.setattr("app.observability.start_http_server", start_http_server_mock)
    monkeypatch.setattr("app.observability.multiprocess.MultiProcessCollector", collector_mock)
    _start_metrics_server(18006)
    registry = start_http_server_mock.call_args.kwargs["registry"]
    collector_mock.assert_called_once_with(registry)
    start_http_server_mock.assert_called_once_with(18006, registry=registry)


def test_start_metrics_server_idempotent(monkeypatch: pytest.MonkeyPatch) -> None:
    from app.observability import _start_metrics_server, reset_observability_for_tests

    reset_observability_for_tests()
    start_http_server_mock = MagicMock()
    monkeypatch.setattr("app.observability.start_http_server", start_http_server_mock)
    _start_metrics_server(18006)
    _start_metrics_server(18006)
    start_http_server_mock.assert_called_once_with(18006)


def test_on_worker_process_init_starts_tracing_and_database(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    reset_observability_for_tests()
    with (
        patch("app.observability.init_tracing") as init_tracing,
        patch("app.observability._init_database") as init_db,
    ):
        _on_worker_process_init()
    init_tracing.assert_called_once()
    init_db.assert_called_once()


def test_on_worker_ready_starts_metrics_only(monkeypatch: pytest.MonkeyPatch) -> None:
    from app.config import get_settings

    reset_observability_for_tests()
    get_settings.cache_clear()
    monkeypatch.setenv("IBEX_WORKER_METRICS_PORT", "18006")
    with (
        patch("app.observability.init_tracing") as init_tracing,
        patch("app.observability._start_metrics_server") as start_metrics,
        patch("app.observability._init_database") as init_db,
    ):
        _on_worker_ready()
    get_settings.cache_clear()
    init_tracing.assert_not_called()
    init_db.assert_not_called()
    start_metrics.assert_called_once_with(18006)
