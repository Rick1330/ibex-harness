"""Shared metadata-only operator session fixtures for unit tests."""

from __future__ import annotations

from datetime import UTC, datetime
from types import SimpleNamespace
from typing import Any
from uuid import uuid4

from app.schemas.operator_sessions import (
    OperatorSession,
    OperatorSessionDetail,
    OperatorSessionTurn,
    SessionTurnEvidence,
)

NOW = datetime(2026, 11, 2, 12, 0, tzinfo=UTC)


def session_values(**overrides: Any) -> dict[str, Any]:
    values: dict[str, Any] = {
        "id": uuid4(),
        "agent_id": uuid4(),
        "external_id": "sess-external",
        "status": "active",
        "model": "gpt-4.1",
        "provider": "openai",
        "directive_version_id": None,
        "turn_count": 2,
        "total_input_tokens": 100,
        "total_output_tokens": 50,
        "total_latency_ms": 1200,
        "last_extracted_turn": 1,
        "lifecycle_revision": 1,
        "evidence_fence_version": 1,
        "created_at": NOW,
        "updated_at": NOW,
        "completed_at": None,
    }
    values.update(overrides)
    return values


def session_record(**overrides: Any) -> OperatorSession:
    return OperatorSession.model_validate(session_values(**overrides))


def session_row(**overrides: Any) -> SimpleNamespace:
    return SimpleNamespace(**session_values(**overrides))


def evidence_record(**overrides: Any) -> SessionTurnEvidence:
    values: dict[str, Any] = {
        "trace_id": "4bf92f3577b34da6a3ce929d0e0e4736",
        "run_id": uuid4(),
        "completeness": "complete",
        "status": "ok",
        "error_code": None,
        "started_at": NOW,
        "ended_at": NOW,
    }
    values.update(overrides)
    return SessionTurnEvidence.model_validate(values)


def turn_values(trace: SessionTurnEvidence | None = None, **overrides: Any) -> dict[str, Any]:
    values: dict[str, Any] = {
        "id": uuid4(),
        "turn_index": 0,
        "request_id": "req-1",
        "input_tokens": 10,
        "output_tokens": 20,
        "model": "gpt-4.1",
        "provider": "openai",
        "latency_ms": 100,
        "is_streaming": False,
        "is_complete": True,
        "created_at": NOW,
        "trace": trace,
    }
    values.update(overrides)
    return values


def turn_record(trace: SessionTurnEvidence | None = None, **overrides: Any) -> OperatorSessionTurn:
    return OperatorSessionTurn.model_validate(turn_values(trace, **overrides))


def turn_row(trace: SessionTurnEvidence | None = None, **overrides: Any) -> SimpleNamespace:
    values = turn_values(trace, **overrides)
    evidence = values.pop("trace")
    values.update(
        {
            "run_id": evidence.run_id if evidence else None,
            "trace_id": evidence.trace_id if evidence else None,
            "completeness": evidence.completeness if evidence else None,
            "status": evidence.status if evidence else None,
            "error_code": evidence.error_code if evidence else None,
            "started_at": evidence.started_at if evidence else None,
            "ended_at": evidence.ended_at if evidence else None,
        }
    )
    return SimpleNamespace(**values)


def session_detail_record(
    turns: list[OperatorSessionTurn] | None = None,
    **overrides: Any,
) -> OperatorSessionDetail:
    return OperatorSessionDetail(
        **session_values(**overrides),
        turns=turns or [],
        turns_truncated=False,
    )
