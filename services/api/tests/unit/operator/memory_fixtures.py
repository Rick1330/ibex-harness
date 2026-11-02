"""Shared metadata-only operator memory fixtures for unit tests."""

from __future__ import annotations

from datetime import UTC, datetime
from types import SimpleNamespace
from typing import Any
from uuid import uuid4

from app.schemas.operator_memories import OperatorMemory

NOW = datetime(2026, 11, 2, 12, 0, tzinfo=UTC)


def memory_values(**overrides: Any) -> dict[str, Any]:
    values: dict[str, Any] = {
        "id": uuid4(),
        "agent_id": uuid4(),
        "session_id": None,
        "category": "factual",
        "status": "active",
        "source": "extracted",
        "confidence": 0.8,
        "usefulness_score": 0.5,
        "content_tokens": 12,
        "retrieval_count": 3,
        "last_retrieved_at": NOW,
        "pii_detected": False,
        "pii_redacted": False,
        "visibility": "agent",
        "pinned": False,
        "tags": ["support"],
        "lifecycle_revision": 1,
        "tombstoned": False,
        "expires_at": None,
        "valid_from": NOW,
        "valid_until": None,
        "observed_at": NOW,
        "created_at": NOW,
        "updated_at": NOW,
        "superseded_by": None,
        "merged_into": None,
    }
    values.update(overrides)
    return values


def memory_record(**overrides: Any) -> OperatorMemory:
    return OperatorMemory.model_validate(memory_values(**overrides))


def memory_row(**overrides: Any) -> SimpleNamespace:
    return SimpleNamespace(**memory_values(**overrides))
