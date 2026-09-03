"""Unit tests for memory schema validation limits."""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import uuid4

import pytest
from pydantic import ValidationError

from app.schemas.limits import MAX_LABELS, validate_memory_metadata, validate_tags
from app.schemas.memories import CreateMemoryRequest, MemoryLabelSchema


def test_validate_tags_rejects_empty_tag() -> None:
    with pytest.raises(ValueError, match="empty"):
        validate_tags(["ok", "  "])


def test_validate_metadata_allows_scalar_leaf_at_max_depth() -> None:
    metadata = {"l1": {"l2": {"l3": {"l4": "leaf-value"}}}}
    validate_memory_metadata(metadata)


def test_validate_metadata_rejects_deep_nesting() -> None:
    nested: dict = {"a": {}}
    current = nested
    for _ in range(6):
        current["child"] = {}
        current = current["child"]
    with pytest.raises(ValueError, match="nesting"):
        validate_memory_metadata(nested)


def test_create_memory_request_rejects_oversized_metadata() -> None:
    agent_id = uuid4()
    with pytest.raises(ValidationError):
        CreateMemoryRequest(
            agent_id=agent_id,
            content="hello",
            metadata={"blob": "x" * 9000},
        )


def test_create_memory_request_rejects_inverted_valid_interval() -> None:
    agent_id = uuid4()
    payload = {
        "agent_id": agent_id,
        "content": "hello",
        "valid_from": datetime(2026, 9, 8, tzinfo=UTC),
        "valid_until": datetime(2026, 9, 1, tzinfo=UTC),
    }
    with pytest.raises(ValidationError, match="valid_until"):
        CreateMemoryRequest(**payload)


def test_create_memory_request_rejects_equal_valid_interval() -> None:
    agent_id = uuid4()
    payload = {
        "agent_id": agent_id,
        "content": "hello",
        "valid_from": datetime(2026, 9, 1, tzinfo=UTC),
        "valid_until": datetime(2026, 9, 1, tzinfo=UTC),
    }
    with pytest.raises(ValidationError, match="valid_until"):
        CreateMemoryRequest(**payload)


def test_create_memory_request_rejects_mixed_timezone_awareness() -> None:
    agent_id = uuid4()
    payload = {
        "agent_id": agent_id,
        "content": "hello",
        "valid_from": datetime(2026, 9, 1, 0, 0, 0),
        "valid_until": datetime(2026, 9, 2, 0, 0, 0, tzinfo=UTC),
    }
    with pytest.raises(ValidationError, match="timezone-aware or both naive"):
        CreateMemoryRequest(**payload)


def test_create_memory_request_rejects_too_many_labels() -> None:
    agent_id = uuid4()
    labels = [MemoryLabelSchema(label="factual", confidence=0.5)] * (MAX_LABELS + 1)
    with pytest.raises(ValidationError):
        CreateMemoryRequest(agent_id=agent_id, content="hello", labels=labels)
