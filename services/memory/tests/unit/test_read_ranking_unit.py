"""Unit tests for read-path composite ranking (milestone 3.D.2)."""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import uuid4

import pytest

from app.read.ranking import (
    FTS_COMPOSITE_RELEVANCE,
    RankedCandidate,
    RankOptions,
    merge_candidates,
    rank_hydrated_hits,
    relevance_for_composite,
)
from app.scoring import RankWeights, composite_score
from tests.unit.read_ranking_support import (
    HydratedHitSeed,
    assert_first_ranked,
    factual_beats_episodic_scenario,
    fts_outranks_stale_weak_vector_scenario,
    hydrated_hit,
    sentinel_boundary_weak_vector_beats_fts_scenario,
    vector_beats_fts_scenario,
)


def test_merge_candidates_vector_wins_on_duplicate() -> None:
    memory_id = uuid4()
    vector = RankedCandidate(memory_id=memory_id, score=0.95, source="vector")
    fts = RankedCandidate(memory_id=memory_id, score=0.8, source="full_text")
    merged = merge_candidates([vector], [fts])
    assert len(merged) == 1
    assert merged[0].source == "vector"
    assert merged[0].score == pytest.approx(0.95)


def test_relevance_for_composite_uses_sentinel_for_fts() -> None:
    fts = RankedCandidate(memory_id=uuid4(), score=0.99, source="full_text")
    assert relevance_for_composite(fts) == FTS_COMPOSITE_RELEVANCE


@pytest.mark.parametrize(
    "scenario",
    [
        pytest.param(factual_beats_episodic_scenario, id="old-factual-beats-fresh-episodic"),
        pytest.param(vector_beats_fts_scenario, id="vector-beats-fts-sentinel"),
        pytest.param(
            sentinel_boundary_weak_vector_beats_fts_scenario,
            id="fts-sentinel-boundary-weak-vector",
        ),
        pytest.param(
            fts_outranks_stale_weak_vector_scenario,
            id="fts-sentinel-outranks-stale-weak-vector",
        ),
    ],
)
def test_rank_hydrated_hits_ordering(scenario) -> None:
    assert_first_ranked(scenario())


def test_hydrated_hit_composite_inputs_matches_write_cache_shape() -> None:
    now = datetime(2026, 8, 29, tzinfo=UTC)
    memory_id = uuid4()
    hit = hydrated_hit(
        HydratedHitSeed(
            memory_id=memory_id,
            category="factual",
            usefulness=0.6,
            confidence=0.8,
            retrieval_count=5,
            age_days=10.0,
        ),
        now=now,
    )
    inputs = hit.composite_inputs(1.0, now=now)
    assert inputs.categories == ("factual",)
    assert inputs.access_frequency == pytest.approx(0.5)
    assert composite_score(inputs) > 0.0


def test_rank_weights_from_settings_change_order() -> None:
    """F4-029: configured RankWeights must change rank_hydrated_hits order."""
    now = datetime(2026, 8, 29, tzinfo=UTC)
    high_rel = uuid4()
    high_rec = uuid4()
    candidates = [
        RankedCandidate(memory_id=high_rel, score=0.95, source="vector"),
        RankedCandidate(memory_id=high_rec, score=0.50, source="vector"),
    ]
    hydrated = {
        high_rel: hydrated_hit(
            HydratedHitSeed(
                memory_id=high_rel,
                similarity=0.95,
                age_days=100.0,
                usefulness=0.1,
                confidence=0.5,
            ),
            now=now,
        ),
        high_rec: hydrated_hit(
            HydratedHitSeed(
                memory_id=high_rec,
                similarity=0.50,
                age_days=0.0,
                usefulness=0.1,
                confidence=0.5,
            ),
            now=now,
        ),
    }
    relevance_heavy = RankWeights(
        relevance=0.80,
        recency=0.05,
        usefulness=0.05,
        confidence=0.05,
        frequency=0.05,
    )
    recency_heavy = RankWeights(
        relevance=0.05,
        recency=0.80,
        usefulness=0.05,
        confidence=0.05,
        frequency=0.05,
    )
    by_relevance = rank_hydrated_hits(
        candidates, hydrated, RankOptions(now=now, weights=relevance_heavy)
    )
    by_recency = rank_hydrated_hits(
        candidates, hydrated, RankOptions(now=now, weights=recency_heavy)
    )
    assert by_relevance[0].id == high_rel
    assert by_recency[0].id == high_rec


def test_multi_label_shortest_half_life_on_read_path() -> None:
    """F4-030a: read ranking uses full categories, not primary alone."""
    now = datetime(2026, 8, 29, tzinfo=UTC)
    primary_only = uuid4()
    multi = uuid4()
    candidates = [
        RankedCandidate(memory_id=primary_only, score=0.90, source="vector"),
        RankedCandidate(memory_id=multi, score=0.90, source="vector"),
    ]
    hydrated = {
        primary_only: hydrated_hit(
            HydratedHitSeed(
                memory_id=primary_only,
                category="factual",
                categories=("factual",),
                similarity=0.90,
                age_days=60.0,
            ),
            now=now,
        ),
        multi: hydrated_hit(
            HydratedHitSeed(
                memory_id=multi,
                category="factual",
                categories=("factual", "episodic"),
                similarity=0.90,
                age_days=60.0,
            ),
            now=now,
        ),
    }
    ranked = rank_hydrated_hits(candidates, hydrated, RankOptions(now=now))
    assert ranked[0].id == primary_only
    assert ranked[1].id == multi
    primary_score = composite_score(
        hydrated[primary_only].composite_inputs(0.90, now=now)
    )
    multi_score = composite_score(hydrated[multi].composite_inputs(0.90, now=now))
    assert multi_score < primary_score


def test_relevance_overrides_replace_the_retrieval_score() -> None:
    stale_winner = uuid4()
    rerank_winner = uuid4()
    candidates = [
        RankedCandidate(memory_id=stale_winner, score=0.95, source="vector"),
        RankedCandidate(memory_id=rerank_winner, score=0.71, source="vector"),
    ]
    hydrated = {
        stale_winner: hydrated_hit(HydratedHitSeed(memory_id=stale_winner)),
        rerank_winner: hydrated_hit(HydratedHitSeed(memory_id=rerank_winner)),
    }
    opts = RankOptions(relevance_overrides={stale_winner: 0.2, rerank_winner: 0.9})

    ranked = rank_hydrated_hits(candidates, hydrated, opts)

    assert [item.id for item in ranked] == [rerank_winner, stale_winner]


def test_relevance_overrides_are_clamped_to_the_unit_interval() -> None:
    memory_id = uuid4()
    candidates = [RankedCandidate(memory_id=memory_id, score=0.5, source="vector")]
    hydrated = {memory_id: hydrated_hit(HydratedHitSeed(memory_id=memory_id))}

    high = rank_hydrated_hits(
        candidates, hydrated, RankOptions(relevance_overrides={memory_id: 3.0})
    )
    low = rank_hydrated_hits(
        candidates, hydrated, RankOptions(relevance_overrides={memory_id: -2.0})
    )

    assert len(high) == 1
    assert low == []


def test_candidates_without_an_override_keep_their_channel_score() -> None:
    overridden = uuid4()
    plain = uuid4()
    candidates = [
        RankedCandidate(memory_id=overridden, score=0.3, source="vector"),
        RankedCandidate(memory_id=plain, score=0.9, source="vector"),
    ]
    hydrated = {
        overridden: hydrated_hit(HydratedHitSeed(memory_id=overridden)),
        plain: hydrated_hit(HydratedHitSeed(memory_id=plain)),
    }

    ranked = rank_hydrated_hits(
        candidates, hydrated, RankOptions(relevance_overrides={overridden: 0.35})
    )

    # `plain` keeps its 0.9 channel score and wins; only `overridden` is rescored.
    assert [item.id for item in ranked] == [plain, overridden]
