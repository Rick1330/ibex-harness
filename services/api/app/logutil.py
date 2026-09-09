"""Request-scoped logging helpers for the management API.

Memory/mcp-memory do not share a single logging Filter pattern: mcp embeds
``request_id=%s`` in printf-style messages. We mirror that style and add a
small Filter so ``%(request_id)s`` works if a formatter is configured later.
"""

from __future__ import annotations

import logging

from app.reqid import get_current


def request_id_for_log() -> str:
    """Return the active request id, or ``-`` outside a request context."""
    return get_current() or "-"


class RequestIdLogFilter(logging.Filter):
    """Attach ``record.request_id`` from the request ContextVar."""

    def filter(self, record: logging.LogRecord) -> bool:
        record.request_id = request_id_for_log()  # type: ignore[attr-defined]
        return True


def install_request_id_log_filter(logger: logging.Logger) -> None:
    """Idempotently install :class:`RequestIdLogFilter` on ``logger``."""
    if any(isinstance(f, RequestIdLogFilter) for f in logger.filters):
        return
    logger.addFilter(RequestIdLogFilter())
