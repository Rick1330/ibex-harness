"""Unit tests for the cross-encoder rerank stage on find_similar (phase 5.A.3)."""

from __future__ import annotations

from dataclasses import replace
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import UUID, uuid4

import pytest

from app.clients.rerank import RerankTimeoutError
from app.config import Settings
from app.read.metrics import RERANK
from app.read.models import MemorySearchResult
from app.read.repository import MemoryReadRepository
from app.vectorstore.base import SearchHit
from tests.unit.find_similar_support import (
    make_hydrated_map as _hydrated_map,
)
from tests.unit.find_similar_support import (
    make_query as _query,
)
from tests.unit.find_similar_support import (
    make_repo as _repo,
)
from tests.unit.find_similar_support import (
    make_result as _result,
)
from tests.unit.find_similar_support import (
    make_settings as _settings,
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


@pytest.mark.asyncio
async def test_hybrid_rerank_keeps_scores_when_the_window_is_already_short() -> None:
    # Two eligible memories, limit 10: a complete window must not be thrown away
    # just because it cannot fill the requested page.
    first, second = UUID(int=1), UUID(int=2)

    results, rerank = await _run_rerank([first, second], scores=[0.20, 0.95], limit=10)

    assert [item.id for item in results] == [second, first]
    rerank.assert_awaited_once()


@pytest.mark.asyncio
async def test_hybrid_rerank_records_an_emptied_page_separately() -> None:
    first, second = UUID(int=1), UUID(int=2)
    before = _rerank_counter("emptied")

    results, _ = await _run_rerank([first, second], scores=[0.01, 0.02])

    assert results
    assert _rerank_counter("emptied") > before


@pytest.mark.asyncio
async def test_hybrid_rerank_never_sends_blocked_content() -> None:
    blocked = UUID(int=1)
    allowed = [UUID(int=2), UUID(int=3)]
    repo, rerank = _reranking_repo([blocked, *allowed], scores=[0.9, 0.8])
    blocked_hit = replace(_result(blocked), content="mail me at a@b.co")
    repo._hydrate_hits = AsyncMock(  # type: ignore[method-assign]
        return_value=_hydrated_map([blocked_hit, *[_result(mid) for mid in allowed]])
    )

    with patch("app.read.repository.full_text_search", AsyncMock(return_value=[])):
        await repo.find_similar(_query(limit=3))

    # The blocked row is filtered before the documents are built, so it never
    # leaves the service.
    assert rerank.await_args.args[1] == ["content", "content"]


@pytest.mark.asyncio
async def test_hybrid_rerank_degrade_does_not_hydrate_the_window_twice() -> None:
    ids = [UUID(int=1), UUID(int=2)]
    repo, _ = _reranking_repo(ids, scores=RerankTimeoutError("slow"))
    repo._hydrate_hits = AsyncMock(  # type: ignore[method-assign]
        return_value=_hydrated_map([_result(mid) for mid in ids])
    )

    with patch("app.read.repository.full_text_search", AsyncMock(return_value=[])):
        await repo.find_similar(_query(limit=2))

    # One row fetch for the rerank window; the fused fallback reuses it.
    assert repo._hydrate_hits.await_count == 1


@pytest.mark.asyncio
async def test_hybrid_rerank_observes_latency_on_degrade() -> None:
    from app.read.metrics import RERANK_LATENCY

    def _observations() -> float:
        return next(
            sample.value
            for sample in RERANK_LATENCY.collect()[0].samples
            if sample.name.endswith("_count")
        )

    before = _observations()

    await _run_rerank([UUID(int=1), UUID(int=2)], scores=RerankTimeoutError("slow"))

    assert _observations() == before + 1


@pytest.mark.asyncio
async def test_hybrid_rerank_does_not_let_a_blocked_row_mask_an_emptied_page() -> None:
    # One blocked row keeps its retrieval relevance; the two allowed rows are all
    # below the rerank floor. The page must fall back to the fused order instead of
    # returning only the blocked row, which the caller's PII filter would drop.
    blocked, allowed_a, allowed_b = UUID(int=1), UUID(int=2), UUID(int=3)
    repo, _ = _reranking_repo([blocked, allowed_a, allowed_b], scores=[0.02, 0.01])
    blocked_hit = replace(_result(blocked), content="mail me at a@b.co")
    repo._hydrate_hits = AsyncMock(  # type: ignore[method-assign]
        return_value=_hydrated_map(
            [blocked_hit, _result(allowed_a), _result(allowed_b)]
        )
    )

    with patch("app.read.repository.full_text_search", AsyncMock(return_value=[])):
        results = await repo.find_similar(_query(limit=3))

    # Fused fallback ran, and the caller still sees a non-empty allowed page.
    assert results
    assert blocked not in {item.id for item in results}


@pytest.mark.asyncio
async def test_rerank_path_suppresses_a_pending_conflict() -> None:
    # The reranked window is the widest the settings allow, so suppression can
    # shorten the page here -- but it must never return both sides.
    winner, loser, third = uuid4(), uuid4(), uuid4()
    group = uuid4()
    repo, _ = _reranking_repo([winner, loser, third], scores=[0.9, 0.2, 0.5])
    repo._hydrate_hits = AsyncMock(  # type: ignore[method-assign]
        return_value=_hydrated_map(
            [
                replace(_result(winner), conflict_groups=(group,)),
                replace(_result(loser), conflict_groups=(group,)),
                _result(third),
            ]
        )
    )

    with patch("app.read.repository.full_text_search", AsyncMock(return_value=[])):
        results = await repo.find_similar(_query(limit=3))

    ids = {item.id for item in results}
    assert len(results) == 2
    assert third in ids
    assert winner in ids
    assert loser not in ids
