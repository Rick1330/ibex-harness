"""Unit tests for scoring-time relevance floor (m3.5.C.3 / ADR-0068)."""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID, uuid4

import pytest

from app.read.ranking import (
    DEFAULT_COMPOSITE_RELEVANCE_FLOOR,
    FTS_COMPOSITE_RELEVANCE,
    RankedCandidate,
    rank_hydrated_hits,
)
from app.scoring.relevance_gate import passes_relevance_floor
from tests.unit.read_ranking_support import HydratedHitSeed, hydrated_hit

_FIXED_NOW = datetime(2026, 9, 5, tzinfo=UTC)


def _rank(
    *seeds: tuple[UUID, float],
    floor: float,
    **hit_kwargs: object,
) -> list[UUID]:
    """Rank vector candidates keyed by (memory_id, retrieval_score)."""
    candidates = [
        RankedCandidate(memory_id=mid, score=score, source="vector") for mid, score in seeds
    ]
    hydrated = {
        mid: hydrated_hit(
            HydratedHitSeed(memory_id=mid, similarity=score, **hit_kwargs),  # type: ignore[arg-type]
            now=_FIXED_NOW,
        )
        for mid, score in seeds
    }
    return [
        item.id
        for item in rank_hydrated_hits(
            candidates, hydrated, now=_FIXED_NOW, relevance_floor=floor
        )
    ]


def test_passes_relevance_floor_boundary_inclusive() -> None:
    assert passes_relevance_floor(0.15, 0.15) is True
    assert passes_relevance_floor(0.14, 0.15) is False
    assert passes_relevance_floor(0.16, 0.15) is True


def test_passes_relevance_floor_rejects_invalid() -> None:
    with pytest.raises(ValueError, match="relevance must be finite"):
        passes_relevance_floor(float("nan"), 0.15)
    with pytest.raises(ValueError, match="floor must be finite"):
        passes_relevance_floor(0.5, float("nan"))
    with pytest.raises(ValueError, match="floor must be finite"):
        passes_relevance_floor(0.5, float("inf"))
    with pytest.raises(ValueError, match="floor must be in"):
        passes_relevance_floor(0.5, 1.5)
    with pytest.raises(ValueError, match="floor must be in"):
        passes_relevance_floor(0.5, -0.01)


def test_rank_excludes_below_floor() -> None:
    low_id, high_id = uuid4(), uuid4()
    ranked = _rank((low_id, 0.10), (high_id, 0.80), floor=0.15)
    assert ranked == [high_id]


def test_rank_includes_exact_floor() -> None:
    mid_id = uuid4()
    assert _rank((mid_id, 0.15), floor=0.15) == [mid_id]


def test_rank_empty_candidates() -> None:
    assert rank_hydrated_hits([], {}, relevance_floor=0.15) == []


def test_rank_all_below_floor_returns_empty() -> None:
    a, b = uuid4(), uuid4()
    assert _rank((a, 0.05), (b, 0.10), floor=0.15) == []


def test_fts_sentinel_passes_default_floor() -> None:
    """FTS sentinel 0.5 must remain above the production floor (< 0.5)."""
    assert FTS_COMPOSITE_RELEVANCE > DEFAULT_COMPOSITE_RELEVANCE_FLOOR
    fts_id = uuid4()
    candidates = [
        RankedCandidate(memory_id=fts_id, score=0.99, source="full_text"),
    ]
    hydrated = {
        fts_id: hydrated_hit(
            HydratedHitSeed(memory_id=fts_id, similarity=0.99, source="full_text"),
            now=_FIXED_NOW,
        ),
    }
    ranked = rank_hydrated_hits(
        candidates,
        hydrated,
        now=_FIXED_NOW,
        relevance_floor=DEFAULT_COMPOSITE_RELEVANCE_FLOOR,
    )
    assert [item.id for item in ranked] == [fts_id]


def test_gate_blocks_stale_frequent_low_relevance_from_outranking() -> None:
    """Classic bug: low-relevance + high non-relevance components must not be scored."""
    noise_id = uuid4()
    relevant_id = uuid4()
    candidates = [
        RankedCandidate(memory_id=noise_id, score=0.05, source="vector"),
        RankedCandidate(memory_id=relevant_id, score=0.90, source="vector"),
    ]
    hydrated = {
        noise_id: hydrated_hit(
            HydratedHitSeed(
                memory_id=noise_id,
                similarity=0.05,
                age_days=1.0,
                usefulness=1.0,
                confidence=1.0,
                retrieval_count=1000,
            ),
            now=_FIXED_NOW,
        ),
        relevant_id: hydrated_hit(
            HydratedHitSeed(
                memory_id=relevant_id,
                category="episodic",
                similarity=0.90,
                age_days=60.0,
                usefulness=0.0,
                confidence=0.0,
                retrieval_count=0,
            ),
            now=_FIXED_NOW,
        ),
    }
    ungated = [
        item.id
        for item in rank_hydrated_hits(
            candidates, hydrated, now=_FIXED_NOW, relevance_floor=0.0
        )
    ]
    gated = [
        item.id
        for item in rank_hydrated_hits(
            candidates, hydrated, now=_FIXED_NOW, relevance_floor=0.15
        )
    ]
    assert ungated == [noise_id, relevant_id]
    assert gated == [relevant_id]
