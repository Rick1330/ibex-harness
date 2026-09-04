"""Unit tests for task_context helpers."""

from __future__ import annotations

from uuid import UUID

from app.task_context import (
    parse_org_id,
    redact_exception_message,
    redact_traceback_for_persistence,
    sanitize_kwargs_for_persistence,
    task_context_from_kwargs,
)

_ORG = "550e8400-e29b-41d4-a716-446655440000"


def test_task_context_from_kwargs_extracts_safe_metadata() -> None:
    ctx = task_context_from_kwargs(
        {
            "org_id": _ORG,
            "agent_id": "agent-1",
            "session_id": "sess-1",
            "memory_content": "must not appear",
        }
    )
    assert ctx == {"org_id": _ORG, "agent_id": "agent-1", "session_id": "sess-1"}


def test_task_context_from_kwargs_empty() -> None:
    assert task_context_from_kwargs(None) == {}
    assert task_context_from_kwargs({}) == {}


def test_parse_org_id_valid() -> None:
    assert parse_org_id({"org_id": _ORG}) == UUID(_ORG)


def test_parse_org_id_invalid_or_missing() -> None:
    assert parse_org_id(None) is None
    assert parse_org_id({}) is None
    assert parse_org_id({"org_id": "not-a-uuid"}) is None


def test_sanitize_kwargs_for_persistence_redacts_sensitive_fields() -> None:
    sanitized = sanitize_kwargs_for_persistence(
        {
            "org_id": _ORG,
            "memory_content": "secret memory text",
            "token": "sk-secret",
        }
    )
    assert sanitized == {"org_id": _ORG}


def test_redact_exception_message_hides_sensitive_text() -> None:
    assert redact_exception_message(RuntimeError("sk-secret-token")) == "[redacted]"


def test_redact_traceback_for_persistence_hides_stack() -> None:
    traceback_text = "Traceback (most recent call last):\n  File secret.py"
    assert redact_traceback_for_persistence(traceback_text) == "[redacted]"
