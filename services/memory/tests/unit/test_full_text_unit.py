"""Unit tests for full-text search helpers (milestone 3.D.1)."""

from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest

from app.read.full_text import (
    FullTextHit,
    FullTextSearchQuery,
    full_text_search,
    is_searchable_query,
)


def _mock_session_factory(rows: list[dict[str, Any]]) -> MagicMock:
    session = MagicMock()
    session.begin = MagicMock(return_value=AsyncMock())
    session.begin.return_value.__aenter__ = AsyncMock(return_value=None)
    session.begin.return_value.__aexit__ = AsyncMock(return_value=None)
    result = MagicMock()
    result.mappings.return_value.all.return_value = rows
    session.execute = AsyncMock(return_value=result)
    factory = MagicMock()
    factory.return_value.__aenter__ = AsyncMock(return_value=session)
    factory.return_value.__aexit__ = AsyncMock(return_value=None)
    return factory


@pytest.mark.parametrize(
    ("query", "expected"),
    [
        ("", False),
        ("   ", False),
        ("preference", True),
    ],
)
def test_is_searchable_query(query: str, expected: bool) -> None:
    assert is_searchable_query(query) is expected


@pytest.mark.asyncio
async def test_full_text_search_returns_hits() -> None:
    org_id = uuid4()
    agent_id = uuid4()
    memory_id = uuid4()
    factory = _mock_session_factory([{"memory_id": str(memory_id), "rank": 0.88}])
    hits = await full_text_search(
        factory,
        FullTextSearchQuery(
            org_id=org_id,
            agent_id=agent_id,
            query_text="dark mode",
            limit=5,
            min_confidence=0.5,
        ),
    )
    assert hits == [FullTextHit(memory_id=memory_id, rank=0.88)]


@pytest.mark.asyncio
async def test_full_text_search_skips_excluded_ids() -> None:
    org_id = uuid4()
    agent_id = uuid4()
    included = uuid4()
    excluded = uuid4()
    factory = _mock_session_factory(
        [
            {"memory_id": str(excluded), "rank": 0.9},
            {"memory_id": str(included), "rank": 0.7},
        ]
    )
    hits = await full_text_search(
        factory,
        FullTextSearchQuery(
            org_id=org_id,
            agent_id=agent_id,
            query_text="dark mode",
            limit=5,
            min_confidence=0.0,
            exclude_ids=frozenset({excluded}),
        ),
    )
    assert hits == [FullTextHit(memory_id=included, rank=0.7)]


@pytest.mark.asyncio
async def test_full_text_search_stops_at_limit_after_exclusions() -> None:
    org_id = uuid4()
    agent_id = uuid4()
    first = uuid4()
    second = uuid4()
    third = uuid4()
    factory = _mock_session_factory(
        [
            {"memory_id": str(first), "rank": 0.9},
            {"memory_id": str(second), "rank": 0.8},
            {"memory_id": str(third), "rank": 0.7},
        ]
    )
    hits = await full_text_search(
        factory,
        FullTextSearchQuery(
            org_id=org_id,
            agent_id=agent_id,
            query_text="dark mode",
            limit=2,
            min_confidence=0.0,
            exclude_ids=frozenset({first}),
        ),
    )
    assert hits == [
        FullTextHit(memory_id=second, rank=0.8),
        FullTextHit(memory_id=third, rank=0.7),
    ]


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "query",
    [
        FullTextSearchQuery(
            org_id=uuid4(),
            agent_id=uuid4(),
            query_text="   ",
            limit=5,
            min_confidence=0.0,
        ),
        FullTextSearchQuery(
            org_id=uuid4(),
            agent_id=uuid4(),
            query_text="query",
            limit=0,
            min_confidence=0.0,
        ),
    ],
    ids=["blank_query", "zero_limit"],
)
async def test_full_text_search_short_circuits_without_db(query: FullTextSearchQuery) -> None:
    hits = await full_text_search(MagicMock(), query)
    assert hits == []
