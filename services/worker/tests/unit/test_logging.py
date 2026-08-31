"""Unit tests for structured logging setup."""

from __future__ import annotations

import json
import logging

from app.logging import JsonFormatter, configure_logging


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
    payload = json.loads(JsonFormatter().format(record))
    assert payload["service"] == "worker"
    assert payload["level"] == "INFO"
    assert payload["message"] == "hello"
    assert payload["task_name"] == "ibex.worker.extraction.noop"


def test_configure_logging_is_idempotent() -> None:
    configure_logging()
    handler_count = len(logging.getLogger().handlers)
    configure_logging()
    assert len(logging.getLogger().handlers) == handler_count
