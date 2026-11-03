"""ADR-0094 §9: a conflict drop is refilled exactly like a confidence/PII drop.

The fallback (hybrid-disabled) path merges a vector page and an optional
full-text page. A hit dropped as the losing side of a pending conflict must not
shorten the page while an eligible full-text candidate waits behind it.
"""

from __future__ import annotations

from dataclasses import replace
from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import UUID, uuid4

import pytest

from app.read.full_text import FullTextHit
from app.read.models import MemorySearchResult
from app.read.ranking import HydratedHit
from app.read.repository import MemoryReadRepository
from app.vectorstore.base import SearchHit
from tests.unit.find_similar_support import make_query, make_settings

CONFLICT = uuid4()


def _result(
    memory_id: UUID,
    *,
    confidence: float = 0.9,
    source: str = "vector",
    conflict_groups: tuple[UUID, ...] = (),
) -> MemorySearchResult:
    now = datetime.now(UTC)
    return MemorySearchResult(
        id=memory_id,
        org_id=uuid4(),
        agent_id=uuid4(),
        # Deterministic and PII-free: a UUID in content can trip the guard's
        # phone/card regexes (hex runs of 13+ digits), which made this file flake.
        content=f"memory body {memory_id.int % 1000}",
        category="factual",
        confidence=confidence,
        status="active",
        similarity=0.95 if source == "vector" else 0.5,
        source=source,  # type: ignore[arg-type]
        created_at=now,
        updated_at=now,
        conflict_groups=conflict_groups,
    )


def _hydrated(results: list[MemorySearchResult]) -> dict[UUID, HydratedHit]:
    now = datetime.now(UTC)
    return {
        item.id: HydratedHit(
            result=item,
            valid_from=now,
            usefulness_score=0.5,
            retrieval_count=0,
        )
        for item in results
    }


@pytest.mark.asyncio
async def test_conflict_drop_in_the_vector_page_refills_from_full_text() -> None:
    """Two vector hits conflict; a third memory is only reachable via full text."""
    loser, winner, fts_only = uuid4(), uuid4(), uuid4()
    store = MagicMock()
    store.search = AsyncMock(
        return_value=[
            SearchHit(memory_id=winner, similarity=0.93),
            SearchHit(memory_id=loser, similarity=0.90),
        ]
    )
    repo = MemoryReadRepository(
        MagicMock(),
        store,
        make_settings(search_hybrid_enabled=False, search_fallback_enabled=True),
    )
    assert repo._settings.search_fallback_enabled
    vector_rows = _hydrated(
        [
            _result(winner, confidence=0.95, conflict_groups=(CONFLICT,)),
            _result(loser, confidence=0.55, conflict_groups=(CONFLICT,)),
        ]
    )
    fts_rows = _hydrated([_result(fts_only, source="full_text")])
    repo._hydrate_hits = AsyncMock(  # type: ignore[method-assign]
        side_effect=[vector_rows, fts_rows]
    )

    with patch(
        "app.read.repository.full_text_search",
        AsyncMock(return_value=[FullTextHit(memory_id=fts_only, rank=0.8)]),
    ) as fts_mock:
        results = await repo.find_similar(
            make_query(query_text="sky colour", limit=2)
        )

    ids = [hit.id for hit in results]
    assert ids == [winner, fts_only] or ids == [fts_only, winner] or set(ids) == {
        winner,
        fts_only,
    }, f"page was {ids}; the suppressed slot must be refilled from full text"
    assert loser not in ids
    assert len(results) == 2, "suppression must not shorten a refillable page"
    fts_mock.assert_awaited_once()


@pytest.mark.asyncio
async def test_conflict_drop_below_a_full_vector_page_still_refills() -> None:
    """The pre-collapse count must not decide whether the refill channel runs."""
    a, b, extra = uuid4(), uuid4(), uuid4()
    store = MagicMock()
    store.search = AsyncMock(
        return_value=[
            SearchHit(memory_id=a, similarity=0.93),
            SearchHit(memory_id=b, similarity=0.92),
        ]
    )
    repo = MemoryReadRepository(
        MagicMock(),
        store,
        make_settings(search_hybrid_enabled=False, search_fallback_enabled=True),
    )
    repo._hydrate_hits = AsyncMock(  # type: ignore[method-assign]
        side_effect=[
            _hydrated(
                [
                    _result(a, confidence=0.9, conflict_groups=(CONFLICT,)),
                    _result(b, confidence=0.5, conflict_groups=(CONFLICT,)),
                ]
            ),
            _hydrated([_result(extra, source="full_text")]),
        ]
    )

    with patch(
        "app.read.repository.full_text_search",
        AsyncMock(return_value=[FullTextHit(memory_id=extra, rank=0.7)]),
    ):
        results = await repo.find_similar(make_query(query_text="sky colour", limit=2))

    assert len(results) == 2
    assert {hit.id for hit in results} == {a, extra}


@pytest.mark.asyncio
async def test_zero_conflict_page_is_unchanged() -> None:
    """Control: with no escalation the fallback page is the vector page."""
    a, b = uuid4(), uuid4()
    store = MagicMock()
    store.search = AsyncMock(
        return_value=[
            SearchHit(memory_id=a, similarity=0.93),
            SearchHit(memory_id=b, similarity=0.92),
        ]
    )
    repo = MemoryReadRepository(
        MagicMock(), store, make_settings(search_hybrid_enabled=False)
    )
    repo._hydrate_hits = AsyncMock(  # type: ignore[method-assign]
        return_value=_hydrated([_result(a), _result(b)])
    )

    with patch("app.read.repository.full_text_search", AsyncMock()) as fts_mock:
        results = await repo.find_similar(make_query(query_text="sky colour", limit=2))

    assert {hit.id for hit in results} == {a, b}
    fts_mock.assert_not_awaited()


@pytest.mark.asyncio
async def test_pii_blocked_winner_does_not_take_the_loser_with_it() -> None:
    """Drop order must not turn one recoverable hit into an empty page.

    The reranked path excludes Tier-1 PII rows *before* ranking precisely so the
    final PII filter cannot empty a page the ranker had already filled. The same
    hazard exists for a conflict pair: if the higher-ranked side is PII-blocked
    after the collapse, the lower-ranked side is already gone.
    """
    winner, loser = uuid4(), uuid4()
    store = MagicMock()
    store.search = AsyncMock(
        return_value=[
            SearchHit(memory_id=winner, similarity=0.93),
            SearchHit(memory_id=loser, similarity=0.90),
        ]
    )
    repo = MemoryReadRepository(
        MagicMock(), store, make_settings(search_hybrid_enabled=False)
    )
    winner_hit = replace(
        _result(winner, confidence=0.95, conflict_groups=(CONFLICT,)),
        content="contact me at someone@example.com",
    )
    repo._hydrate_hits = AsyncMock(  # type: ignore[method-assign]
        return_value=_hydrated(
            [winner_hit, _result(loser, confidence=0.55, conflict_groups=(CONFLICT,))]
        )
    )

    with patch("app.read.repository.full_text_search", AsyncMock(return_value=[])):
        results = await repo.find_similar(make_query(query_text="contact", limit=5))

    assert [hit.id for hit in results] == [loser], (
        "the covered claim is that the higher-ranked side survives and the page "
        "is not shortened; a PII block on that side must fall back to the other "
        "side rather than returning nothing"
    )


@pytest.mark.asyncio
async def test_a_suppressed_supplement_hit_is_replaced_by_the_next_one() -> None:
    """The supplement is sized by the page, not by the deficit.

    If the first full-text hit is itself the losing side of the conflict, the
    next eligible match must still be able to fill the slot.
    """
    winner, loser, third = uuid4(), uuid4(), uuid4()
    disputed_fts, clean_fts = uuid4(), uuid4()
    store = MagicMock()
    store.search = AsyncMock(
        return_value=[
            SearchHit(memory_id=winner, similarity=0.93),
            SearchHit(memory_id=loser, similarity=0.91),
            SearchHit(memory_id=third, similarity=0.90),
        ]
    )
    repo = MemoryReadRepository(
        MagicMock(), store, make_settings(search_hybrid_enabled=False)
    )
    repo._hydrate_hits = AsyncMock(  # type: ignore[method-assign]
        side_effect=[
            _hydrated(
                [
                    _result(winner, confidence=0.95, conflict_groups=(CONFLICT,)),
                    _result(loser, confidence=0.90, conflict_groups=(CONFLICT,)),
                    _result(third, confidence=0.85),
                ]
            ),
            _hydrated(
                [
                    _result(disputed_fts, source="full_text", conflict_groups=(CONFLICT,)),
                    _result(clean_fts, source="full_text"),
                ]
            ),
        ]
    )

    with patch(
        "app.read.repository.full_text_search",
        AsyncMock(
            return_value=[
                FullTextHit(memory_id=disputed_fts, rank=0.9),
                FullTextHit(memory_id=clean_fts, rank=0.5),
            ]
        ),
    ) as fts_mock:
        results = await repo.find_similar(make_query(query_text="sky colour", limit=3))

    # The SQL page must leave room for the excluded vector ids: the supplement is
    # sized by the page, not by the one-slot deficit.
    assert fts_mock.await_args.args[1].limit == 3 + 3

    ids = {hit.id for hit in results}
    assert len(results) == 3, f"page was {len(results)}; a suppressed supplement hit must be replaced"
    assert clean_fts in ids
    assert disputed_fts not in ids


@pytest.mark.asyncio
async def test_pii_recheck_runs_once_per_hydrated_row() -> None:
    """A refill pass must not re-scan (or re-count) rows the first pass judged."""
    from app.read.metrics import PII_RECONFIRM

    first, second, third = uuid4(), uuid4(), uuid4()
    store = MagicMock()
    store.search = AsyncMock(
        return_value=[
            SearchHit(memory_id=first, similarity=0.93),
            SearchHit(memory_id=second, similarity=0.91),
            SearchHit(memory_id=third, similarity=0.90),
        ]
    )
    repo = MemoryReadRepository(
        MagicMock(),
        store,
        make_settings(search_hybrid_enabled=True, rerank_enabled=False),
    )
    repo._hydrate_hits = AsyncMock(  # type: ignore[method-assign]
        return_value=_hydrated(
            [
                _result(first, confidence=0.95, conflict_groups=(CONFLICT,)),
                _result(second, confidence=0.90, conflict_groups=(CONFLICT,)),
                _result(third, confidence=0.85),
            ]
        )
    )
    before = PII_RECONFIRM.labels(result="passed")._value.get()

    with patch("app.read.repository.full_text_search", AsyncMock(return_value=[])):
        await repo.find_similar(make_query(query_text="conflict", limit=2))

    after = PII_RECONFIRM.labels(result="passed")._value.get()
    assert after - before == 3, "each hydrated row must be re-checked exactly once"
