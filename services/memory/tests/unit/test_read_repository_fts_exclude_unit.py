"""Unit tests: FTS exclusion keeps below-floor vector IDs out of the fallback set."""

from __future__ import annotations

from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest

from app.config import Settings
from app.read.full_text import FullTextHit
from app.read.models import FindSimilarQuery
from app.read.ranking import RankedCandidate
from app.read.repository import MemoryReadRepository
from app.vectorstore.base import SearchHit


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


def _hydrate_row(*, memory_id, org_id, agent_id, now: datetime) -> dict:
    return {
        "id": str(memory_id),
        "org_id": str(org_id),
        "agent_id": str(agent_id),
        "content": "dark mode preference",
        "category": "preference",
        "confidence": 0.9,
        "status": "active",
        "created_at": now,
        "updated_at": now,
        "valid_from": now,
        "usefulness_score": 0.5,
        "retrieval_count": 0,
    }


@pytest.mark.asyncio
async def test_find_similar_excludes_below_floor_vector_ids_from_fts() -> None:
    """Below-floor vector hits must stay in FTS exclude_ids so they cannot reappear."""
    org_id = uuid4()
    agent_id = uuid4()
    low_id = uuid4()
    high_id = uuid4()
    fts_only_id = uuid4()
    now = datetime.now(UTC)

    store = MagicMock()
    store.search = AsyncMock(
        return_value=[
            SearchHit(memory_id=low_id, similarity=0.05),
            SearchHit(memory_id=high_id, similarity=0.90),
        ]
    )
    settings = Settings(
        database_url="postgresql+asyncpg://x",
        search_fallback_enabled=True,
        composite_relevance_floor=0.15,
    )
    repo = MemoryReadRepository(
        _session_factory_with_rows(
            [
                _hydrate_row(memory_id=low_id, org_id=org_id, agent_id=agent_id, now=now),
                _hydrate_row(memory_id=high_id, org_id=org_id, agent_id=agent_id, now=now),
                _hydrate_row(memory_id=fts_only_id, org_id=org_id, agent_id=agent_id, now=now),
            ]
        ),
        store,
        settings,
    )

    with patch(
        "app.read.repository.full_text_search",
        new_callable=AsyncMock,
    ) as fts:
        fts.return_value = [
            FullTextHit(memory_id=fts_only_id, rank=0.8),
            FullTextHit(memory_id=low_id, rank=0.7),
        ]
        results = await repo.find_similar(
            FindSimilarQuery(
                org_id=org_id,
                agent_id=agent_id,
                query_embedding=[0.0] * 1024,
                query_text="dark mode preference",
                limit=5,
                min_similarity=0.0,
            )
        )

    assert fts.await_count == 1
    exclude_ids = fts.await_args.args[1].exclude_ids
    assert low_id in exclude_ids
    assert high_id in exclude_ids
    result_ids = [item.id for item in results]
    assert low_id not in result_ids
    assert high_id in result_ids
    assert len(result_ids) == len(set(result_ids))
