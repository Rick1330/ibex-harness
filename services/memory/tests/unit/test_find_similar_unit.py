"""Unit tests for find_similar merge and validation (milestone 3.D.1)."""

from __future__ import annotations

import asyncio
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
        results = await repo.find_similar(_query(query_text=case.query_text, limit=case.limit))
    fts_mock.assert_awaited_once()
    return results


async def _assert_full_text_skipped(
    *,
    ids: list[UUID],
    limit: int,
    query_text: str = "query",
    settings: Settings | None = None,
) -> list[MemorySearchResult]:
    """Run find_similar and assert the full-text channel never ran."""
    store = MagicMock()
    store.search = AsyncMock(
        return_value=[SearchHit(memory_id=mid, similarity=0.88) for mid in ids]
    )
    repo = _repo(store, settings)
    repo._hydrate_hits = AsyncMock(  # type: ignore[method-assign]
        return_value=_hydrated_map([_result(mid) for mid in ids])
    )
    with patch("app.read.repository.full_text_search", AsyncMock()) as fts_mock:
        results = await repo.find_similar(_query(query_text=query_text, limit=limit))
    fts_mock.assert_not_awaited()
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
    search_request = store.search.await_args.args[0]
    from app.vectorstore.base import SearchMode

    assert search_request.mode is SearchMode.USER_RETRIEVAL
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


def test_fts_candidates_clamp_unbounded_ts_rank_to_unit_similarity() -> None:
    """ts_rank_cd can exceed 1 (e.g. 2.0); HTTP/context similarity must stay in [0, 1]."""
    from app.read.repository import _clamp_unit_interval, _fts_candidates

    assert _clamp_unit_interval(2.0) == 1.0
    assert _clamp_unit_interval(-0.5) == 0.0
    assert _clamp_unit_interval(0.42) == pytest.approx(0.42)

    memory_id = uuid4()
    candidates = _fts_candidates(
        [FullTextHit(memory_id=memory_id, rank=2.0)],
        cap=5,
    )
    assert len(candidates) == 1
    assert candidates[0].memory_id == memory_id
    assert candidates[0].source == "full_text"
    assert candidates[0].score == pytest.approx(1.0)


@pytest.mark.asyncio
async def test_find_similar_no_fallback_at_exact_limit() -> None:
    results = await _assert_full_text_skipped(ids=[uuid4(), uuid4()], limit=2)

    assert len(results) == 2


@pytest.mark.asyncio
async def test_find_similar_no_fts_when_vector_fills_limit() -> None:
    ids = [uuid4() for _ in range(4)]
    store = MagicMock()
    store.search = AsyncMock(
        return_value=[
            SearchHit(memory_id=mid, similarity=0.95 - index * 0.01)
            for index, mid in enumerate(ids)
        ]
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
    invalid = _query(limit=0)

    with pytest.raises(ValueError, match="limit"):
        await repo.find_similar(invalid)


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
    results = await _assert_full_text_skipped(
        ids=[uuid4()],
        limit=3,
        query_text="dark mode",
        settings=_settings(search_fallback_enabled=False),
    )

    assert len(results) == 1


@pytest.mark.asyncio
@pytest.mark.parametrize("min_confidence", [-0.1, 1.1])
async def test_find_similar_rejects_bad_min_confidence(min_confidence: float) -> None:
    repo = _repo()
    invalid = _query(limit=1, min_confidence=min_confidence)

    with pytest.raises(ValueError, match="min_confidence"):
        await repo.find_similar(invalid)


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


@dataclass(frozen=True, slots=True)
class HybridCase:
    vector_ids: list[UUID]
    fts_id: UUID
    limit: int
    fts_rank: float = 0.42
    query_text: str = "dark mode preference"


async def _run_hybrid(case: HybridCase, *, similarity: float = 0.9) -> list[MemorySearchResult]:
    store = MagicMock()
    store.search = AsyncMock(
        return_value=[SearchHit(memory_id=mid, similarity=similarity) for mid in case.vector_ids]
    )
    repo = _repo(store, _settings(search_hybrid_enabled=True))
    fts_result = _result(case.fts_id, source="full_text")
    # One hydrate call: the fused union is hydrated together.
    repo._hydrate_hits = AsyncMock(  # type: ignore[method-assign]
        return_value=_hydrated_map(
            [
                *[_result(mid, confidence=0.9) for mid in case.vector_ids],
                fts_result,
            ]
        )
    )
    with patch(
        "app.read.repository.full_text_search",
        AsyncMock(return_value=[FullTextHit(memory_id=case.fts_id, rank=case.fts_rank)]),
    ) as fts_mock:
        results = await repo.find_similar(_query(query_text=case.query_text, limit=case.limit))
    fts_mock.assert_awaited_once()
    return results


@pytest.mark.asyncio
async def test_hybrid_admits_an_exact_match_into_a_full_vector_page() -> None:
    # The defect the fallback gate had: vector fills the page, so the exact-token
    # match never entered the candidate set even though it was retrieved.
    vector_ids = [uuid4() for _ in range(3)]
    fts_id = uuid4()

    # Weak vector matches: an exact-token hit must be able to displace one. The
    # FTS candidate still scores through the 0.5 composite sentinel, which is why
    # the scoring half of 5.A.2 (real ts_rank) is a follow-up.
    results = await _run_hybrid(
        HybridCase(vector_ids=vector_ids, fts_id=fts_id, limit=3), similarity=0.3
    )

    assert any(item.id == fts_id for item in results)
    assert len(results) == 3


@pytest.mark.asyncio
async def test_hybrid_keeps_the_vector_score_when_both_channels_match() -> None:
    shared = uuid4()
    store = MagicMock()
    store.search = AsyncMock(return_value=[SearchHit(memory_id=shared, similarity=0.77)])
    repo = _repo(store, _settings(search_hybrid_enabled=True))
    repo._hydrate_hits = AsyncMock(  # type: ignore[method-assign]
        return_value=_hydrated_map([_result(shared, source="vector")])
    )

    with patch(
        "app.read.repository.full_text_search",
        AsyncMock(return_value=[FullTextHit(memory_id=shared, rank=0.2)]),
    ):
        results = await repo.find_similar(_query(query_text="shared", limit=3))

    assert [item.id for item in results] == [shared]
    assert results[0].source == "vector"


@pytest.mark.asyncio
async def test_hybrid_is_off_by_default_and_keeps_the_fallback_gate() -> None:
    # Default settings keep the previous behaviour: no full-text call at a full page.
    await _assert_full_text_skipped(ids=[uuid4(), uuid4()], limit=2)


@pytest.mark.asyncio
async def test_hybrid_skips_full_text_for_an_unsearchable_query() -> None:
    await _assert_full_text_skipped(
        ids=[uuid4()],
        limit=3,
        query_text="   ",
        settings=_settings(search_hybrid_enabled=True),
    )


@pytest.mark.asyncio
async def test_hybrid_admission_is_the_fused_window_bounded_by_limit() -> None:
    # Both channels return a full page; the fused window, not the union, is what
    # gets hydrated, so hydration cost stays at the page size.
    vector_ids = [uuid4() for _ in range(4)]
    fts_id = uuid4()
    store = MagicMock()
    store.search = AsyncMock(
        return_value=[SearchHit(memory_id=mid, similarity=0.8) for mid in vector_ids]
    )
    repo = _repo(store, _settings(search_hybrid_enabled=True))
    repo._hydrate_hits = AsyncMock(  # type: ignore[method-assign]
        return_value=_hydrated_map([_result(mid, confidence=0.9) for mid in [*vector_ids, fts_id]])
    )

    with patch(
        "app.read.repository.full_text_search",
        AsyncMock(return_value=[FullTextHit(memory_id=fts_id, rank=0.4)]),
    ):
        await repo.find_similar(_query(query_text="dark mode", limit=3))

    admitted = repo._hydrate_hits.await_args.kwargs["candidates"]
    assert len(admitted) == 3
    assert {item.memory_id for item in admitted} <= {*vector_ids, fts_id}


@pytest.mark.asyncio
async def test_hybrid_channels_run_concurrently() -> None:
    """Both channels must be in flight at once, not one after the other.

    Each side waits on a two-party barrier, so a sequential implementation
    deadlocks and the timeout turns it into a failure.
    """
    barrier = asyncio.Barrier(2)
    vector_id = uuid4()

    async def _vector_search(_request: object) -> list[SearchHit]:
        await barrier.wait()
        return [SearchHit(memory_id=vector_id, similarity=0.9)]

    async def _full_text(_factory: object, _query: object) -> list[FullTextHit]:
        await barrier.wait()
        return []

    store = MagicMock()
    store.search = AsyncMock(side_effect=_vector_search)
    repo = _repo(store, _settings(search_hybrid_enabled=True))
    repo._hydrate_hits = AsyncMock(  # type: ignore[method-assign]
        return_value=_hydrated_map([_result(vector_id)])
    )

    with patch("app.read.repository.full_text_search", _full_text):
        results = await asyncio.wait_for(
            repo.find_similar(_query(query_text="dark mode", limit=3)),
            timeout=5,
        )

    assert [item.id for item in results] == [vector_id]


@pytest.mark.asyncio
async def test_hybrid_refills_the_page_when_an_admitted_candidate_is_dropped() -> None:
    # limit=1: the vector id wins the fused rank-1 tie on id order, then hydration
    # drops it below min_confidence. The eligible full-text hit behind it must still
    # fill the page instead of the request returning nothing.
    vector_id = UUID(int=1)
    fts_id = UUID(int=2)
    store = MagicMock()
    store.search = AsyncMock(return_value=[SearchHit(memory_id=vector_id, similarity=0.9)])
    repo = _repo(store, _settings(search_hybrid_enabled=True))
    hydrations: list[list[UUID]] = []

    async def _hydrate(**kwargs: object) -> dict[UUID, HydratedHit]:
        ids = [item.memory_id for item in kwargs["candidates"]]  # type: ignore[union-attr]
        hydrations.append(ids)
        if fts_id in ids:
            return _hydrated_map([_result(fts_id, source="full_text")])
        return {}

    repo._hydrate_hits = AsyncMock(side_effect=_hydrate)  # type: ignore[method-assign]

    with patch(
        "app.read.repository.full_text_search",
        AsyncMock(return_value=[FullTextHit(memory_id=fts_id, rank=0.4)]),
    ):
        results = await repo.find_similar(_query(query_text="dark mode", limit=1))

    assert [item.id for item in results] == [fts_id]
    assert hydrations == [[vector_id], [fts_id]]
