"""Request ID generation and context (mirrors packages/reqid Go)."""

from __future__ import annotations

from contextvars import ContextVar
from uuid import UUID, uuid4

from uuid6 import uuid7

HEADER = "X-Request-ID"

_request_id_var: ContextVar[str | None] = ContextVar("ibex_api_request_id", default=None)


def new_id() -> str:
    """Generate a UUID v7 string; fall back to v4 if v7 fails."""
    try:
        return str(uuid7())
    except (OSError, ValueError, RuntimeError):
        return str(uuid4())


def resolve_inbound(raw: str | None) -> str:
    """Return raw when it is a valid UUID, otherwise a new UUID v7."""
    if raw is None:
        return new_id()
    trimmed = raw.strip()
    if not trimmed:
        return new_id()
    try:
        UUID(trimmed)
    except ValueError:
        return new_id()
    return trimmed


def set_current(request_id: str) -> None:
    _request_id_var.set(request_id)


def get_current() -> str | None:
    return _request_id_var.get()


def require_current() -> str:
    value = get_current()
    if value is None:
        return new_id()
    return value
