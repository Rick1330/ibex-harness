"""JSON log formatter for the operator service (AGENTS.md §10.3)."""

from __future__ import annotations

import json
import logging
from typing import Any

_RESERVED = frozenset(vars(logging.makeLogRecord({})))


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, Any] = {
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }
        for key, value in vars(record).items():
            if key in _RESERVED or key.startswith("_"):
                continue
            payload[key] = value
        if record.exc_info:
            payload["exception"] = self.formatException(record.exc_info)
        return json.dumps(payload, default=str, separators=(",", ":"))


def configure_logging() -> None:
    logger = logging.getLogger("app")
    if getattr(logger, "_ibex_json_configured", False):
        return
    handler = logging.StreamHandler()
    handler.setFormatter(JsonFormatter())
    logger.addHandler(handler)
    logger.setLevel(logging.INFO)
    logger.propagate = False
    logger._ibex_json_configured = True  # type: ignore[attr-defined]
