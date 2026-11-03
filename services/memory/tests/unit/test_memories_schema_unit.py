"""Unit tests for CreateMemoryRequest schema validators."""

from __future__ import annotations

from uuid import uuid4

import pytest
from pydantic import ValidationError as PydanticValidationError

from app.schemas.memories import CreateMemoryRequest


def test_create_memory_tags_validator_returns_tags() -> None:
    request = CreateMemoryRequest(agent_id=uuid4(), content="x", tags=["alpha", "beta"])
    assert request.tags == ["alpha", "beta"]


def test_create_memory_rejects_session_revision_without_session_id() -> None:
    with pytest.raises(PydanticValidationError, match="requires session_id"):
        CreateMemoryRequest(agent_id=uuid4(), content="x", expected_session_revision=1)
