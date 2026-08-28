"""Unit tests for memory schema validation limits."""

from __future__ import annotations

from uuid import uuid4

import pytest
from pydantic import ValidationError

from app.schemas.limits import validate_memory_metadata, validate_tags
from app.schemas.memories import CreateMemoryRequest


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
    with pytest.raises(ValidationError):
        CreateMemoryRequest(
            agent_id=uuid4(),
            content="hello",
            metadata={"blob": "x" * 9000},
        )
