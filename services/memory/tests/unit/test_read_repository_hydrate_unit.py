"""Unit tests for MemoryReadRepository._hydrate_hits."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock
from uuid import UUID, uuid4

import pytest

from app.config import Settings
from app.read.ranking import RankedCandidate
from app.read.repository import MemoryReadRepository


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


@dataclass(frozen=True, slots=True)
class _RowSeed:
    memory_id: UUID
    org_id: UUID
    agent_id: UUID
    now: datetime
    categories: tuple[str, ...] | str | None = None


def _row(seed: _RowSeed) -> dict:
    row: dict[str, object] = {
        "id": str(seed.memory_id),
        "org_id": str(seed.org_id),
        "agent_id": str(seed.agent_id),
        "content": "dark mode",
        "category": "factual",
        "confidence": 0.9,
        "status": "active",
        "created_at": seed.now,
        "updated_at": seed.now,
        "valid_from": seed.now,
        "usefulness_score": 0.5,
        "retrieval_count": 0,
    }
    if seed.categories is not None:
        row["categories"] = (
            list(seed.categories) if isinstance(seed.categories, tuple) else seed.categories
        )
    return row


@pytest.mark.asyncio
async def test_hydrate_hits_maps_rows_to_search_results() -> None:
    org_id = uuid4()
    agent_id = uuid4()
    memory_id = uuid4()
    now = datetime.now(UTC)
    repo = MemoryReadRepository(
        _session_factory_with_rows(
            [_row(_RowSeed(memory_id=memory_id, org_id=org_id, agent_id=agent_id, now=now))]
        ),
        MagicMock(),
        Settings(database_url="postgresql+asyncpg://x"),
    )
    candidates = [
        RankedCandidate(memory_id=memory_id, score=0.88, source="vector"),
    ]
    hydrated = await repo._hydrate_hits(
        org_id=org_id,
        candidates=candidates,
        min_confidence=0.5,
    )
    assert memory_id in hydrated
    assert hydrated[memory_id].result.similarity == pytest.approx(0.88)
    assert hydrated[memory_id].result.source == "vector"
    assert hydrated[memory_id].usefulness_score == pytest.approx(0.5)
    # Rows without a labels array fall back to primary category (F4-030a).
    assert hydrated[memory_id].result.categories == ("factual",)


@pytest.mark.asyncio
async def test_hydrate_hits_maps_multi_label_categories() -> None:
    org_id = uuid4()
    agent_id = uuid4()
    memory_id = uuid4()
    now = datetime.now(UTC)
    repo = MemoryReadRepository(
        _session_factory_with_rows(
            [
                _row(
                    _RowSeed(
                        memory_id=memory_id,
                        org_id=org_id,
                        agent_id=agent_id,
                        now=now,
                        categories=("factual", "episodic"),
                    )
                )
            ]
        ),
        MagicMock(),
        Settings(database_url="postgresql+asyncpg://x"),
    )
    hydrated = await repo._hydrate_hits(
        org_id=org_id,
        candidates=[RankedCandidate(memory_id=memory_id, score=0.88, source="vector")],
        min_confidence=0.5,
    )
    assert hydrated[memory_id].result.categories == ("factual", "episodic")


@pytest.mark.asyncio
async def test_hydrate_hits_maps_scalar_string_categories() -> None:
    """Defensive: a scalar categories string must not be iterated char-by-char."""
    org_id = uuid4()
    agent_id = uuid4()
    memory_id = uuid4()
    now = datetime.now(UTC)
    repo = MemoryReadRepository(
        _session_factory_with_rows(
            [
                _row(
                    _RowSeed(
                        memory_id=memory_id,
                        org_id=org_id,
                        agent_id=agent_id,
                        now=now,
                        categories="preference",
                    )
                )
            ]
        ),
        MagicMock(),
        Settings(database_url="postgresql+asyncpg://x"),
    )
    hydrated = await repo._hydrate_hits(
        org_id=org_id,
        candidates=[RankedCandidate(memory_id=memory_id, score=0.88, source="vector")],
        min_confidence=0.5,
    )
    assert hydrated[memory_id].result.categories == ("preference",)


@pytest.mark.asyncio
async def test_hydrate_hits_returns_empty_for_empty_candidates() -> None:
    repo = MemoryReadRepository(
        MagicMock(),
        MagicMock(),
        Settings(database_url="postgresql+asyncpg://x"),
    )
    hydrated = await repo._hydrate_hits(
        org_id=uuid4(),
        candidates=[],
        min_confidence=0.0,
    )
    assert hydrated == {}


@pytest.mark.asyncio
async def test_hydrate_hits_skips_rows_without_matching_candidate() -> None:
    org_id = uuid4()
    row_memory_id = uuid4()
    unrelated_candidate_id = uuid4()
    now = datetime.now(UTC)
    repo = MemoryReadRepository(
        _session_factory_with_rows(
            [
                _row(
                    _RowSeed(
                        memory_id=row_memory_id,
                        org_id=org_id,
                        agent_id=uuid4(),
                        now=now,
                    )
                )
            ]
        ),
        MagicMock(),
        Settings(database_url="postgresql+asyncpg://x"),
    )
    hydrated = await repo._hydrate_hits(
        org_id=org_id,
        candidates=[
            RankedCandidate(
                memory_id=unrelated_candidate_id,
                score=0.88,
                source="vector",
            )
        ],
        min_confidence=0.0,
    )
    assert hydrated == {}
