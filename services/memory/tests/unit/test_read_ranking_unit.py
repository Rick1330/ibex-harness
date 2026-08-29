"""Unit tests for read-path composite ranking (milestone 3.D.2)."""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import uuid4

import pytest

from app.read.ranking import (
    FTS_COMPOSITE_RELEVANCE,
    RankedCandidate,
    merge_candidates,
    relevance_for_composite,
)
from app.scoring import composite_score
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
        )
    )
    inputs = hit.composite_inputs(1.0, now=now)
    assert inputs.categories == ("factual",)
    assert inputs.access_frequency == pytest.approx(0.5)
    assert composite_score(inputs) > 0.0
