"""Unit tests for find_similar merge and validation (milestone 3.D.1)."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import UUID, uuid4

import pytest

from app.config import Settings
from app.read.full_text import FullTextHit
from app.read.models import FindSimilarQuery, MemorySearchResult
from app.read.ranking import HydratedHit
from app.read.repository import MemoryReadRepository
from app.vectorstore.base import SearchHit


def _settings(**kwargs: object) -> Settings:
    return Settings(database_url="postgresql+asyncpg://x", **kwargs)


def _result(memory_id, *, confidence: float = 0.9, source: str = "vector") -> MemorySearchResult:
    now = datetime.now(UTC)
    return MemorySearchResult(
        id=memory_id,
        org_id=uuid4(),
        agent_id=uuid4(),
        content="content",
        category="factual",
        confidence=confidence,
        status="active",
        similarity=0.95 if source == "vector" else 0.5,
        source=source,  # type: ignore[arg-type]
        created_at=now,
        updated_at=now,
    )


def _hydrated_map(results: list[MemorySearchResult]) -> dict[UUID, HydratedHit]:
    now = datetime.now(UTC)
    return {
        item.id: HydratedHit(
            result=item,
            valid_from=now - timedelta(days=30),
            usefulness_score=0.5,
            retrieval_count=0,
        )
        for item in results
    }


def _query(**kwargs: object) -> FindSimilarQuery:
    defaults: dict[str, object] = {
        "org_id": uuid4(),
        "agent_id": uuid4(),
        "query_embedding": [0.0] * 1024,
        "query_text": "q",
        "limit": 5,
    }
    defaults.update(kwargs)
    return FindSimilarQuery(**defaults)  # type: ignore[arg-type]


def _repo(
  store: MagicMock | None = None,
  settings: Settings | None = None,
) -> MemoryReadRepository:
    return MemoryReadRepository(MagicMock(), store or MagicMock(), settings or _settings())


def _vector_repo(
    memory_ids: list[UUID],
    *,
    similarities: list[float] | None = None,
    confidences: list[float] | None = None,
) -> tuple[MemoryReadRepository, MagicMock]:
    store = MagicMock()
    store.search = AsyncMock(
        return_value=[
            SearchHit(
                memory_id=memory_id,
                similarity=similarities[index] if similarities is not None else 0.9,
            )
            for index, memory_id in enumerate(memory_ids)
        ]
    )
    repo = _repo(store)
    repo._hydrate_hits = AsyncMock(  # type: ignore[method-assign]
        return_value=_hydrated_map(
            [
                _result(
                    memory_id,
                    confidence=confidences[index] if confidences is not None else 0.9,
                )
                for index, memory_id in enumerate(memory_ids)
            ]
        )
    )
    return repo, store


@dataclass(frozen=True, slots=True)
class SparseFtsFallbackCase:
    vector_ids: list[UUID]
    fts_id: UUID
    limit: int
    fts_rank: float = 0.42
    query_text: str = "dark mode preference"


async def _run_sparse_fts_fallback(case: SparseFtsFallbackCase) -> list[MemorySearchResult]:
    store = MagicMock()
    store.search = AsyncMock(
        return_value=[SearchHit(memory_id=mid, similarity=0.9) for mid in case.vector_ids]
    )
    repo = _repo(store)
    vector_results = [_result(mid) for mid in case.vector_ids]
    fts_result = _result(case.fts_id, source="full_text")
    repo._hydrate_hits = AsyncMock(  # type: ignore[method-assign]
        side_effect=[
            _hydrated_map(vector_results),
            _hydrated_map([fts_result]),
        ]
    )
    with patch(
        "app.read.repository.full_text_search",
        AsyncMock(return_value=[FullTextHit(memory_id=case.fts_id, rank=case.fts_rank)]),
    ) as fts_mock:
        results = await repo.find_similar(
            _query(query_text=case.query_text, limit=case.limit)
        )
    fts_mock.assert_awaited_once()
    return results


@pytest.mark.asyncio
async def test_find_similar_vector_only_at_limit() -> None:
    org_id = uuid4()
    agent_id = uuid4()
    ids = [uuid4() for _ in range(3)]
    repo, store = _vector_repo(ids)

    results = await repo.find_similar(
        _query(
            org_id=org_id,
            agent_id=agent_id,
            query_text="preferences dark mode",
            limit=3,
        )
    )
    assert len(results) == 3
    store.search.assert_awaited_once()
    repo._hydrate_hits.assert_awaited_once()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("vector_count", "limit", "fts_rank", "expected_len"),
    [
        (1, 3, 0.42, 2),
        (15, 20, 0.55, 16),
    ],
)
async def test_find_similar_sparse_fts_fallback(
    vector_count: int,
    limit: int,
    fts_rank: float,
    expected_len: int,
) -> None:
    vector_ids = [uuid4() for _ in range(vector_count)]
    fts_id = uuid4()
    results = await _run_sparse_fts_fallback(
        SparseFtsFallbackCase(
            vector_ids=vector_ids,
            fts_id=fts_id,
            limit=limit,
            fts_rank=fts_rank,
        )
    )
    assert len(results) == expected_len
    assert any(item.source == "vector" for item in results)
    if expected_len > vector_count:
        assert any(item.source == "full_text" for item in results)


@pytest.mark.asyncio
async def test_find_similar_no_fallback_at_exact_limit() -> None:
    ids = [uuid4(), uuid4()]
    store = MagicMock()
    store.search = AsyncMock(
        return_value=[SearchHit(memory_id=mid, similarity=0.88) for mid in ids]
    )
    repo = _repo(store)
    repo._hydrate_hits = AsyncMock(  # type: ignore[method-assign]
        return_value=_hydrated_map([_result(mid) for mid in ids])
    )

    with patch(
        "app.read.repository.full_text_search",
        AsyncMock(),
    ) as fts_mock:
        results = await repo.find_similar(_query(query_text="query", limit=2))

    fts_mock.assert_not_awaited()
    assert len(results) == 2


@pytest.mark.asyncio
async def test_find_similar_no_fts_when_vector_fills_limit() -> None:
    ids = [uuid4() for _ in range(4)]
    store = MagicMock()
    store.search = AsyncMock(
        return_value=[SearchHit(memory_id=mid, similarity=0.95 - index * 0.01) for index, mid in enumerate(ids)]
    )
    repo = _repo(store)
    repo._hydrate_hits = AsyncMock(  # type: ignore[method-assign]
        return_value=_hydrated_map([_result(mid) for mid in ids[:3]])
    )

    with patch("app.read.repository.full_text_search", AsyncMock()) as fts_mock:
        results = await repo.find_similar(
            _query(
                query_text="dark mode preference",
                limit=3,
            )
        )

    fts_mock.assert_not_awaited()
    assert len(results) == 3
    assert all(item.source == "vector" for item in results)


@pytest.mark.asyncio
async def test_find_similar_both_empty() -> None:
    store = MagicMock()
    store.search = AsyncMock(return_value=[])
    repo = _repo(store)
    repo._hydrate_hits = AsyncMock(return_value={})  # type: ignore[method-assign]

    with patch("app.read.repository.full_text_search", AsyncMock(return_value=[])):
        results = await repo.find_similar(_query(query_text="nothing here"))
    assert results == []


@pytest.mark.asyncio
async def test_find_similar_skips_fts_for_blank_query() -> None:
    store = MagicMock()
    store.search = AsyncMock(return_value=[])
    repo = _repo(store)
    repo._hydrate_hits = AsyncMock(return_value={})  # type: ignore[method-assign]

    with patch("app.read.repository.full_text_search", AsyncMock()) as fts_mock:
        results = await repo.find_similar(_query(query_text="   "))
    fts_mock.assert_not_awaited()
    assert results == []


@pytest.mark.asyncio
async def test_find_similar_rejects_bad_limit() -> None:
    repo = _repo()
    with pytest.raises(ValueError, match="limit"):
        await repo.find_similar(_query(limit=0))


@pytest.mark.asyncio
async def test_find_similar_min_confidence_boundary() -> None:
    org_id = uuid4()
    agent_id = uuid4()
    mid = uuid4()
    repo, _store = _vector_repo([mid], similarities=[0.99], confidences=[1.0])

    results = await repo.find_similar(
        _query(
            org_id=org_id,
            agent_id=agent_id,
            query_text="test",
            limit=1,
            min_confidence=1.0,
        )
    )
    assert len(results) == 1
    repo._hydrate_hits.assert_awaited_once()
    assert repo._hydrate_hits.await_args.kwargs["min_confidence"] == 1.0


@pytest.mark.asyncio
async def test_find_similar_fallback_disabled() -> None:
    vector_id = uuid4()
    store = MagicMock()
    store.search = AsyncMock(return_value=[SearchHit(memory_id=vector_id, similarity=0.9)])
    repo = _repo(store, settings=_settings(search_fallback_enabled=False))
    repo._hydrate_hits = AsyncMock(  # type: ignore[method-assign]
        return_value=_hydrated_map([_result(vector_id)])
    )

    with patch("app.read.repository.full_text_search", AsyncMock()) as fts_mock:
        results = await repo.find_similar(_query(query_text="dark mode"))

    fts_mock.assert_not_awaited()
    assert len(results) == 1


@pytest.mark.asyncio
@pytest.mark.parametrize("min_confidence", [-0.1, 1.1])
async def test_find_similar_rejects_bad_min_confidence(min_confidence: float) -> None:
    repo = _repo()
    with pytest.raises(ValueError, match="min_confidence"):
        await repo.find_similar(_query(limit=1, min_confidence=min_confidence))


@pytest.mark.asyncio
async def test_find_similar_drops_unhydrated_candidates() -> None:
    vector_id = uuid4()
    missing_id = uuid4()
    store = MagicMock()
    store.search = AsyncMock(
        return_value=[
            SearchHit(memory_id=vector_id, similarity=0.95),
            SearchHit(memory_id=missing_id, similarity=0.9),
        ]
    )
    repo = _repo(store)
    repo._hydrate_hits = AsyncMock(  # type: ignore[method-assign]
        return_value=_hydrated_map([_result(vector_id)])
    )

    with patch("app.read.repository.full_text_search", AsyncMock(return_value=[])) as fts_mock:
        results = await repo.find_similar(_query(limit=2))

    fts_mock.assert_awaited_once()
    repo._hydrate_hits.assert_awaited_once()
    assert len(results) == 1
    assert results[0].id == vector_id
