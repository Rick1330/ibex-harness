"""Unit tests for the cross-encoder rerank stage on find_similar (phase 5.A.3)."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import UUID, uuid4

import pytest

from app.clients.rerank import RerankTimeoutError
from app.config import Settings
from app.read.metrics import RERANK
from app.read.models import FindSimilarQuery, MemorySearchResult
from app.read.ranking import HydratedHit
from app.read.repository import MemoryReadRepository
from app.vectorstore.base import SearchHit


def _settings(**kwargs: object) -> Settings:
    return Settings(database_url="postgresql+asyncpg://x", **kwargs)


def _result(memory_id: UUID, *, confidence: float = 0.9) -> MemorySearchResult:
    now = datetime.now(UTC)
    return MemorySearchResult(
        id=memory_id,
        org_id=uuid4(),
        agent_id=uuid4(),
        content="content",
        category="factual",
        confidence=confidence,
        status="active",
        similarity=0.95,
        source="vector",
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
        "query_text": "dark mode",
        "limit": 4,
    }
    defaults.update(kwargs)
    return FindSimilarQuery(**defaults)  # type: ignore[arg-type]


def _repo(
    store: MagicMock | None = None,
    settings: Settings | None = None,
    *,
    rerank_client: object | None = None,
) -> MemoryReadRepository:
    return MemoryReadRepository(
        MagicMock(),
        store or MagicMock(),
        settings or _settings(),
        rerank_client=rerank_client,  # type: ignore[arg-type]
    )

def _rerank_counter(result: str) -> float:
    return RERANK.labels(result=result)._value.get()


def _store_for(ids: list[UUID]) -> MagicMock:
    store = MagicMock()
    store.search = AsyncMock(
        return_value=[SearchHit(memory_id=mid, similarity=0.9) for mid in ids]
    )
    return store


def _reranking_repo(
    ids: list[UUID],
    *,
    scores: list[float] | Exception,
    settings: Settings | None = None,
) -> tuple[MemoryReadRepository, AsyncMock]:
    """Hybrid repo with an injected reranker; returns the repo and the fake client call."""
    client = MagicMock()
    if isinstance(scores, Exception):
        client.rerank = AsyncMock(side_effect=scores)
    else:
        client.rerank = AsyncMock(return_value=scores)
    repo = _repo(
        _store_for(ids),
        settings or _settings(search_hybrid_enabled=True, rerank_enabled=True),
        rerank_client=client,
    )
    return repo, client.rerank



async def _run_rerank(
    ids: list[UUID],
    *,
    scores: list[float] | Exception,
    settings: Settings | None = None,
    limit: int | None = None,
) -> tuple[list[MemorySearchResult], AsyncMock]:
    """Run a hybrid search with an injected reranker; returns results and the fake call."""
    repo, rerank = _reranking_repo(ids, scores=scores, settings=settings)
    repo._hydrate_hits = AsyncMock(  # type: ignore[method-assign]
        return_value=_hydrated_map([_result(mid) for mid in ids])
    )
    with patch("app.read.repository.full_text_search", AsyncMock(return_value=[])):
        results = await repo.find_similar(_query(limit=limit or len(ids)))
    return results, rerank


@pytest.mark.asyncio
async def test_hybrid_rerank_orders_by_cross_encoder_score() -> None:
    first, second = UUID(int=1), UUID(int=2)

    results, rerank = await _run_rerank([first, second], scores=[0.20, 0.95])

    assert [item.id for item in results] == [second, first]
    assert rerank.await_args.args[1] == ["content", "content"]


@pytest.mark.asyncio
async def test_hybrid_rerank_timeout_degrades_to_the_fused_order() -> None:
    first, second = UUID(int=1), UUID(int=2)
    before = _rerank_counter("degraded")

    results, _ = await _run_rerank([first, second], scores=RerankTimeoutError("slow"))

    assert [item.id for item in results] == [first, second]
    assert _rerank_counter("degraded") > before


@pytest.mark.asyncio
async def test_hybrid_rerank_does_not_run_when_disabled() -> None:
    memory_id = uuid4()

    _, rerank = await _run_rerank(
        [memory_id],
        scores=[0.9],
        settings=_settings(search_hybrid_enabled=True),
    )

    rerank.assert_not_awaited()


@pytest.mark.asyncio
async def test_hybrid_rerank_window_is_capped() -> None:
    ids = [UUID(int=i) for i in range(1, 5)]

    _, rerank = await _run_rerank(
        ids,
        scores=[0.9, 0.8],
        settings=_settings(
            search_hybrid_enabled=True, rerank_enabled=True, rerank_max_candidates=2
        ),
    )

    assert len(rerank.await_args.args[1]) == 2


@pytest.mark.asyncio
async def test_hybrid_rerank_falls_back_when_every_score_is_below_the_floor() -> None:
    first, second = UUID(int=1), UUID(int=2)

    results, _ = await _run_rerank([first, second], scores=[0.01, 0.02])

    # Rerank said "irrelevant"; a short page must not hide the fused order.
    assert [item.id for item in results] == [first, second]


@pytest.mark.asyncio
async def test_hybrid_rerank_skips_a_single_candidate_window() -> None:
    memory_id = uuid4()
    before = _rerank_counter("skipped")

    results, rerank = await _run_rerank([memory_id], scores=[0.9], limit=1)

    assert [item.id for item in results] == [memory_id]
    rerank.assert_not_awaited()
    assert _rerank_counter("skipped") > before
