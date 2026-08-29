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
    RankScenario,
    assert_first_ranked,
    hydrated_hit,
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
        pytest.param(
            lambda: _factual_beats_episodic_scenario(),
            id="old-factual-beats-fresh-episodic",
        ),
        pytest.param(
            lambda: _vector_beats_fts_scenario(),
            id="vector-beats-fts-sentinel",
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


def _factual_beats_episodic_scenario() -> RankScenario:
    factual_id = uuid4()
    episodic_id = uuid4()
    fixed_now = datetime(2026, 8, 29, tzinfo=UTC)
    return RankScenario(
        candidates=(
            RankedCandidate(memory_id=episodic_id, score=0.90, source="vector"),
            RankedCandidate(memory_id=factual_id, score=0.90, source="vector"),
        ),
        hydrated={
            episodic_id: hydrated_hit(
                HydratedHitSeed(
                    memory_id=episodic_id,
                    category="episodic",
                    similarity=0.90,
                    age_days=14.0,
                )
            ),
            factual_id: hydrated_hit(
                HydratedHitSeed(
                    memory_id=factual_id,
                    category="factual",
                    similarity=0.90,
                    age_days=90.0,
                )
            ),
        },
        expected_first=factual_id,
        fixed_now=fixed_now,
    )


def _vector_beats_fts_scenario() -> RankScenario:
    vector_id = uuid4()
    fts_id = uuid4()
    fixed_now = datetime(2026, 8, 29, tzinfo=UTC)
    return RankScenario(
        candidates=(
            RankedCandidate(memory_id=fts_id, score=0.9, source="full_text"),
            RankedCandidate(memory_id=vector_id, score=0.85, source="vector"),
        ),
        hydrated={
            fts_id: hydrated_hit(
                HydratedHitSeed(
                    memory_id=fts_id,
                    category="episodic",
                    similarity=0.9,
                    source="full_text",
                    age_days=1.0,
                )
            ),
            vector_id: hydrated_hit(
                HydratedHitSeed(
                    memory_id=vector_id,
                    category="episodic",
                    similarity=0.85,
                    source="vector",
                    age_days=1.0,
                )
            ),
        },
        expected_first=vector_id,
        fixed_now=fixed_now,
    )
