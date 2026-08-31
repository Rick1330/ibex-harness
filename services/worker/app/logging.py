"""Structured JSON logging for the Celery worker process."""

from __future__ import annotations

import json
import logging
import sys
from datetime import UTC, datetime
from typing import Any

_SERVICE_NAME = "worker"

_CONFIGURED = False


class JsonFormatter(logging.Formatter):
    """Emit one JSON object per log line (CODING_STANDARDS.md)."""

    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, Any] = {
            "timestamp": datetime.now(UTC).isoformat(),
            "level": record.levelname,
            "service": _SERVICE_NAME,
            "message": record.getMessage(),
        }
        for key in (
            "task_name",
            "task_id",
            "org_id",
            "agent_id",
            "duration_ms",
            "queue",
        ):
            if hasattr(record, key):
                payload[key] = getattr(record, key)
        if record.exc_info:
            payload["exception"] = self.formatException(record.exc_info)
        return json.dumps(payload, default=str)


def configure_logging(level: int = logging.INFO) -> None:
    """Configure root logger once for worker and beat processes."""
    global _CONFIGURED
    if _CONFIGURED:
        return
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(JsonFormatter())
    root = logging.getLogger()
    root.handlers.clear()
    root.addHandler(handler)
    root.setLevel(level)
    _CONFIGURED = True
