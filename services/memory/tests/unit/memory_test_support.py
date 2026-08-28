"""Shared factories for memory write unit tests."""

from __future__ import annotations

from dataclasses import replace
from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

from app.write.models import MemoryRow


def sample_memory_row(**overrides: object) -> MemoryRow:
    now = datetime.now(tz=UTC)
    row = MemoryRow(
        id=uuid4(),
        org_id=uuid4(),
        agent_id=uuid4(),
        content="hello",
        content_tokens=1,
        category="factual",
        confidence=0.8,
        status="active",
        source="user_provided",
        pii_detected=False,
        pii_redacted=False,
        session_id=None,
        visibility="agent",
        pinned=False,
        tags=(),
        metadata={},
        retrieval_count=0,
        usefulness_score=0.5,
        valid_from=now,
        valid_until=None,
        created_at=now,
        updated_at=now,
    )
    if overrides:
        return replace(row, **overrides)  # type: ignore[arg-type]
    return row


def mock_async_session_factory() -> MagicMock:
    """Async session factory with begin() context manager for orchestrator tests."""
    mock_session = MagicMock()
    mock_begin = MagicMock()
    mock_begin.__aenter__ = AsyncMock(return_value=mock_session)
    mock_begin.__aexit__ = AsyncMock(return_value=None)
    mock_session.begin = MagicMock(return_value=mock_begin)
    mock_cm = MagicMock()
    mock_cm.__aenter__ = AsyncMock(return_value=mock_session)
    mock_cm.__aexit__ = AsyncMock(return_value=None)
    return MagicMock(return_value=mock_cm)
