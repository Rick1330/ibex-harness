"""Unit tests for scoring-time relevance floor (m3.5.C.3 / ADR-0068)."""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import uuid4

import pytest

from app.read.ranking import (
    DEFAULT_COMPOSITE_RELEVANCE_FLOOR,
    FTS_COMPOSITE_RELEVANCE,
    RankedCandidate,
    rank_hydrated_hits,
)
from app.scoring.relevance_gate import passes_relevance_floor
from tests.unit.read_ranking_support import HydratedHitSeed, hydrated_hit


def test_passes_relevance_floor_boundary_inclusive() -> None:
    assert passes_relevance_floor(0.15, 0.15) is True
    assert passes_relevance_floor(0.14, 0.15) is False
    assert passes_relevance_floor(0.16, 0.15) is True


def test_passes_relevance_floor_rejects_invalid() -> None:
    with pytest.raises(ValueError):
        passes_relevance_floor(float("nan"), 0.15)
    with pytest.raises(ValueError):
        passes_relevance_floor(0.5, 1.5)


def test_rank_excludes_below_floor() -> None:
    low_id = uuid4()
    high_id = uuid4()
    now = datetime(2026, 9, 5, tzinfo=UTC)
    candidates = [
        RankedCandidate(memory_id=low_id, score=0.10, source="vector"),
        RankedCandidate(memory_id=high_id, score=0.80, source="vector"),
    ]
    hydrated = {
        low_id: hydrated_hit(HydratedHitSeed(memory_id=low_id, similarity=0.10)),
        high_id: hydrated_hit(HydratedHitSeed(memory_id=high_id, similarity=0.80)),
    }
    ranked = rank_hydrated_hits(
        candidates, hydrated, now=now, relevance_floor=0.15
    )
    assert [item.id for item in ranked] == [high_id]


def test_rank_includes_exact_floor() -> None:
    mid_id = uuid4()
    now = datetime(2026, 9, 5, tzinfo=UTC)
    candidates = [RankedCandidate(memory_id=mid_id, score=0.15, source="vector")]
    hydrated = {
        mid_id: hydrated_hit(HydratedHitSeed(memory_id=mid_id, similarity=0.15)),
    }
    ranked = rank_hydrated_hits(
        candidates, hydrated, now=now, relevance_floor=0.15
    )
    assert [item.id for item in ranked] == [mid_id]


def test_rank_empty_candidates() -> None:
    assert rank_hydrated_hits([], {}, relevance_floor=0.15) == []


def test_rank_all_below_floor_returns_empty() -> None:
    a = uuid4()
    b = uuid4()
    now = datetime(2026, 9, 5, tzinfo=UTC)
    candidates = [
        RankedCandidate(memory_id=a, score=0.05, source="vector"),
        RankedCandidate(memory_id=b, score=0.10, source="vector"),
    ]
    hydrated = {
        a: hydrated_hit(HydratedHitSeed(memory_id=a, similarity=0.05)),
        b: hydrated_hit(HydratedHitSeed(memory_id=b, similarity=0.10)),
    }
    ranked = rank_hydrated_hits(
        candidates, hydrated, now=now, relevance_floor=0.15
    )
    assert ranked == []


def test_fts_sentinel_passes_default_floor() -> None:
    """FTS sentinel 0.5 must remain above the production floor (< 0.5)."""
    assert FTS_COMPOSITE_RELEVANCE > DEFAULT_COMPOSITE_RELEVANCE_FLOOR
    fts_id = uuid4()
    now = datetime(2026, 9, 5, tzinfo=UTC)
    candidates = [
        RankedCandidate(memory_id=fts_id, score=0.99, source="full_text"),
    ]
    hydrated = {
        fts_id: hydrated_hit(
            HydratedHitSeed(memory_id=fts_id, similarity=0.99, source="full_text")
        ),
    }
    ranked = rank_hydrated_hits(
        candidates,
        hydrated,
        now=now,
        relevance_floor=DEFAULT_COMPOSITE_RELEVANCE_FLOOR,
    )
    assert [item.id for item in ranked] == [fts_id]


def test_gate_blocks_stale_frequent_low_relevance_from_outranking() -> None:
    """Classic bug: low-relevance + high non-relevance components must not be scored."""
    noise_id = uuid4()
    relevant_id = uuid4()
    now = datetime(2026, 9, 5, tzinfo=UTC)
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
                retrieval_count=100,
            )
        ),
        relevant_id: hydrated_hit(
            HydratedHitSeed(
                memory_id=relevant_id,
                similarity=0.90,
                age_days=30.0,
                usefulness=0.1,
                confidence=0.5,
                retrieval_count=0,
            )
        ),
    }
    # Without gate (floor=0), noise can compete; with gate, only relevant remains.
    ungated = rank_hydrated_hits(
        candidates, hydrated, now=now, relevance_floor=0.0
    )
    gated = rank_hydrated_hits(
        candidates, hydrated, now=now, relevance_floor=0.15
    )
    assert len(ungated) == 2
    assert [item.id for item in gated] == [relevant_id]
