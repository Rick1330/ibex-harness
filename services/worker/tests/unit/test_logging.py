"""Unit tests for structured logging setup."""

from __future__ import annotations

import json
import logging
from collections.abc import Iterator

import pytest

import app.logging as logging_module
from app.logging import JsonFormatter, configure_logging


@pytest.fixture
def reset_logging_state() -> Iterator[None]:
    """Snapshot and restore process-global logging configuration."""
    root = logging.getLogger()
    saved_handlers = root.handlers[:]
    saved_level = root.level
    saved_configured = logging_module._CONFIGURED
    yield
    root.handlers.clear()
    for handler in saved_handlers:
        root.addHandler(handler)
    root.setLevel(saved_level)
    logging_module._CONFIGURED = saved_configured


def test_json_formatter_emits_required_fields() -> None:
    record = logging.LogRecord(
        name="worker",
        level=logging.INFO,
        pathname=__file__,
        lineno=1,
        msg="hello",
        args=(),
        exc_info=None,
    )
    record.task_name = "ibex.worker.extraction.noop"
    record.task_id = "abc"
    record.trace_id = "trace-1"
    payload = json.loads(JsonFormatter().format(record))
    assert payload["service"] == "worker"
    assert payload["level"] == "INFO"
    assert payload["message"] == "hello"
    assert payload["task_name"] == "ibex.worker.extraction.noop"
    assert payload["trace_id"] == "trace-1"


def test_json_formatter_includes_exception() -> None:
    import sys

    try:
        raise RuntimeError("boom")
    except RuntimeError:
        exc_info = sys.exc_info()
        record = logging.LogRecord(
            name="worker",
            level=logging.ERROR,
            pathname=__file__,
            lineno=1,
            msg="failed",
            args=(),
            exc_info=exc_info,
        )
    payload = json.loads(JsonFormatter().format(record))
    assert "exception" in payload
    assert "RuntimeError: boom" in payload["exception"]


def test_configure_logging_is_idempotent(reset_logging_state: None) -> None:
    logging_module._CONFIGURED = False
    configure_logging()
    handler_count = len(logging.getLogger().handlers)
    configure_logging()
    assert len(logging.getLogger().handlers) == handler_count
