"""Offline floor-sweep evidence for ADR-0068 (no Postgres required).

The live ranking_quality bench uses ``min_similarity=0.5`` (see
``bench_ranking_quality.py``). Every gold-set vector hit that reaches
``rank_hydrated_hits`` therefore has composite relevance >= 0.5.

Candidate scoring-time floors {0.10, 0.15, 0.20, 0.25, 0.30} all lie strictly
below that retrieval cutoff (and below FTS_COMPOSITE_RELEVANCE=0.5), so they
are *neutral* on gold_set_v1 precision@5 / recall@10 — identical to floor=0.0.

This module encodes that invariant as a unit test and also verifies that the
chosen floor still excludes classic low-relevance noise when retrieval is
deliberately opened (min_similarity lowered).
"""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import uuid4

from app.read.ranking import FTS_COMPOSITE_RELEVANCE, RankedCandidate, rank_hydrated_hits
from app.scoring.relevance_gate import passes_relevance_floor
from tests.unit.read_ranking_support import HydratedHitSeed, hydrated_hit

# Gold-set bench retrieval cutoff (bench_ranking_quality._evaluate_query).
_GOLD_SET_MIN_SIMILARITY = 0.5
_FLOOR_CANDIDATES = (0.10, 0.15, 0.20, 0.25, 0.30)
_CHOSEN_FLOOR = 0.15


def test_floor_candidates_strictly_below_gold_set_retrieval_and_fts() -> None:
    for floor in _FLOOR_CANDIDATES:
        assert floor < _GOLD_SET_MIN_SIMILARITY
        assert floor < FTS_COMPOSITE_RELEVANCE


def test_gold_set_compatible_relevances_pass_all_candidate_floors() -> None:
    """Any relevance that survives gold-set ANN ( >= 0.5 ) passes every sweep floor."""
    for relevance in (0.5, 0.51, 0.7, 0.9, 1.0):
        for floor in _FLOOR_CANDIDATES:
            assert passes_relevance_floor(relevance, floor)


def test_floor_sweep_neutral_on_gold_set_like_candidate_set() -> None:
    """Ranking a gold-set-like slate is identical for floor in {0.0} ∪ candidates."""
    now = datetime(2026, 9, 5, tzinfo=UTC)
    ids = [uuid4() for _ in range(3)]
    relevances = (0.55, 0.72, 0.91)
    candidates = [
        RankedCandidate(memory_id=mid, score=rel, source="vector")
        for mid, rel in zip(ids, relevances, strict=True)
    ]
    hydrated = {
        mid: hydrated_hit(
            HydratedHitSeed(memory_id=mid, similarity=rel, age_days=1.0 + i)
        )
        for i, (mid, rel) in enumerate(zip(ids, relevances, strict=True))
    }
    baseline = [item.id for item in rank_hydrated_hits(
        candidates, hydrated, now=now, relevance_floor=0.0
    )]
    for floor in _FLOOR_CANDIDATES:
        ranked = [
            item.id
            for item in rank_hydrated_hits(
                candidates, hydrated, now=now, relevance_floor=floor
            )
        ]
        assert ranked == baseline


def test_chosen_floor_excludes_noise_when_retrieval_opened() -> None:
    """With low-relevance noise present, floor=0.15 drops it; floor=0.0 keeps it."""
    now = datetime(2026, 9, 5, tzinfo=UTC)
    noise = uuid4()
    keep = uuid4()
    candidates = [
        RankedCandidate(memory_id=noise, score=0.08, source="vector"),
        RankedCandidate(memory_id=keep, score=0.80, source="vector"),
    ]
    hydrated = {
        noise: hydrated_hit(
            HydratedHitSeed(
                memory_id=noise,
                similarity=0.08,
                usefulness=1.0,
                confidence=1.0,
                retrieval_count=100,
            )
        ),
        keep: hydrated_hit(HydratedHitSeed(memory_id=keep, similarity=0.80)),
    }
    ungated = [
        item.id
        for item in rank_hydrated_hits(
            candidates, hydrated, now=now, relevance_floor=0.0
        )
    ]
    gated = [
        item.id
        for item in rank_hydrated_hits(
            candidates, hydrated, now=now, relevance_floor=_CHOSEN_FLOOR
        )
    ]
    assert set(ungated) == {noise, keep}
    assert gated == [keep]
