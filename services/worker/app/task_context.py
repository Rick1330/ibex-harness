"""Shared task kwargs context extraction (logging, tracing, dead-letter)."""

from __future__ import annotations

from typing import Any
from uuid import UUID

_REDACTED = "[redacted]"
_SAFE_KWARG_KEYS = frozenset({"org_id", "agent_id", "session_id"})


def task_context_from_kwargs(kwargs: dict[str, Any] | None) -> dict[str, str]:
    """Return safe string metadata from task kwargs (no memory content)."""
    extra: dict[str, str] = {}
    if kwargs is None:
        return extra
    for key in ("org_id", "agent_id", "session_id"):
        if value := kwargs.get(key):
            extra[key] = str(value)
    return extra


def sanitize_kwargs_for_persistence(kwargs: dict[str, Any] | None) -> dict[str, str]:
    """Return only approved ID fields for dead-letter persistence."""
    if not kwargs:
        return {}
    return {
        key: str(value)
        for key, value in kwargs.items()
        if key in _SAFE_KWARG_KEYS and value is not None
    }


def redact_exception_message(_exc: BaseException | None) -> str:
    """Return a bounded, non-sensitive exception message for persistence."""
    return _REDACTED


def redact_traceback_for_persistence(_traceback_text: str) -> str:
    """Return a bounded traceback placeholder (no stack text persisted)."""
    return _REDACTED


def parse_org_id(kwargs: dict[str, Any] | None) -> UUID | None:
    """Parse org_id from task kwargs when present and valid."""
    if not kwargs:
        return None
    raw = kwargs.get("org_id")
    if raw is None:
        return None
    try:
        return UUID(str(raw))
    except (TypeError, ValueError):
        return None
