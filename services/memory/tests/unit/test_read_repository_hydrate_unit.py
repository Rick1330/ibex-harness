"""Unit tests for MemoryReadRepository._hydrate."""

from __future__ import annotations

from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest

from app.config import Settings
from app.read.repository import MemoryReadRepository, RankedCandidate


def _session_factory_with_rows(rows: list[dict]) -> MagicMock:
    mock_session = MagicMock()
    mock_begin = MagicMock()
    mock_begin.__aenter__ = AsyncMock(return_value=mock_session)
    mock_begin.__aexit__ = AsyncMock(return_value=None)
    mock_session.begin = MagicMock(return_value=mock_begin)
    result = MagicMock()
    result.mappings.return_value.all.return_value = rows
    mock_session.execute = AsyncMock(return_value=result)
    factory = MagicMock()
    factory.return_value.__aenter__ = AsyncMock(return_value=mock_session)
    factory.return_value.__aexit__ = AsyncMock(return_value=None)
    return factory


@pytest.mark.asyncio
async def test_hydrate_maps_rows_to_search_results() -> None:
    org_id = uuid4()
    agent_id = uuid4()
    memory_id = uuid4()
    now = datetime.now(UTC)
    repo = MemoryReadRepository(
        _session_factory_with_rows(
            [
                {
                    "id": str(memory_id),
                    "org_id": str(org_id),
                    "agent_id": str(agent_id),
                    "content": "dark mode",
                    "category": "factual",
                    "confidence": 0.9,
                    "status": "active",
                    "created_at": now,
                    "updated_at": now,
                }
            ]
        ),
        MagicMock(),
        Settings(database_url="postgresql+asyncpg://x"),
    )
    candidates = [
        RankedCandidate(memory_id=memory_id, score=0.88, source="vector"),
    ]
    hydrated = await repo._hydrate(
        org_id=org_id,
        candidates=candidates,
        min_confidence=0.5,
    )
    assert memory_id in hydrated
    assert hydrated[memory_id].similarity == pytest.approx(0.88)
    assert hydrated[memory_id].source == "vector"


@pytest.mark.asyncio
async def test_hydrate_skips_rows_without_matching_candidate() -> None:
    org_id = uuid4()
    memory_id = uuid4()
    now = datetime.now(UTC)
    repo = MemoryReadRepository(
        _session_factory_with_rows(
            [
                {
                    "id": str(memory_id),
                    "org_id": str(org_id),
                    "agent_id": uuid4(),
                    "content": "x",
                    "category": "factual",
                    "confidence": 0.9,
                    "status": "active",
                    "created_at": now,
                    "updated_at": now,
                }
            ]
        ),
        MagicMock(),
        Settings(database_url="postgresql+asyncpg://x"),
    )
    hydrated = await repo._hydrate(
        org_id=org_id,
        candidates=[],
        min_confidence=0.0,
    )
    assert hydrated == {}
