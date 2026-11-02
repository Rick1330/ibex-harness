"""Unit tests for reciprocal rank fusion (phase 5.A.2)."""

from __future__ import annotations

from uuid import UUID, uuid4

import pytest

from app.read.fusion import RRF_K_DEFAULT, reciprocal_rank_fusion
from app.read.ranking import RankedCandidate, fuse_candidates


def _ids(count: int) -> list[UUID]:
    return [uuid4() for _ in range(count)]


def test_default_k_is_the_published_constant() -> None:
    assert RRF_K_DEFAULT == 60


def test_scores_are_reciprocal_ranks_and_ranks_start_at_one() -> None:
    [first, second] = _ids(2)

    fused = reciprocal_rank_fusion([[first, second]])

    assert [item.memory_id for item in fused] == [first, second]
    assert fused[0].score == pytest.approx(1 / (RRF_K_DEFAULT + 1))
    assert fused[1].score == pytest.approx(1 / (RRF_K_DEFAULT + 2))


def test_a_hit_both_channels_agree_on_outranks_a_single_channel_hit() -> None:
    [shared, vector_only, fts_only] = _ids(3)

    fused = reciprocal_rank_fusion([[shared, vector_only], [fts_only, shared]])

    assert fused[0].memory_id == shared
    # Rank 1 in one channel and rank 2 in the other: both terms are summed.
    assert fused[0].score == pytest.approx(
        1 / (RRF_K_DEFAULT + 1) + 1 / (RRF_K_DEFAULT + 2)
    )
    # A rank-1 hit in one channel outranks a rank-2 hit in the other.
    assert fused[1].memory_id == fts_only
    assert fused[1].score == pytest.approx(1 / (RRF_K_DEFAULT + 1))
    assert fused[2].score == pytest.approx(1 / (RRF_K_DEFAULT + 2))


def test_ties_break_deterministically_by_id() -> None:
    [left, right] = sorted(_ids(2), key=str)

    fused = reciprocal_rank_fusion([[left], [right]])

    assert [item.memory_id for item in fused] == [left, right]
    assert fused[0].score == fused[1].score


def test_empty_and_single_channel_inputs() -> None:
    memory_id = uuid4()

    assert reciprocal_rank_fusion([]) == []
    assert reciprocal_rank_fusion([[], []]) == []
    assert [item.memory_id for item in reciprocal_rank_fusion([[], [memory_id]])] == [memory_id]


def test_k_must_be_positive() -> None:
    with pytest.raises(ValueError, match="RRF k"):
        reciprocal_rank_fusion([[uuid4()]], k=0)


def test_fuse_candidates_keeps_channel_scores_and_vector_wins_duplicates() -> None:
    shared, vector_only, fts_only = _ids(3)
    vector = [
        RankedCandidate(memory_id=shared, score=0.81, source="vector"),
        RankedCandidate(memory_id=vector_only, score=0.64, source="vector"),
    ]
    fts = [
        RankedCandidate(memory_id=fts_only, score=0.42, source="full_text"),
        # The same memory also matched full text; the vector score must survive.
        RankedCandidate(memory_id=shared, score=0.9, source="full_text"),
    ]

    fused = fuse_candidates(vector, fts)

    # shared matched both channels; fts_only ranked 1st in its channel, so it
    # outranks vector_only, which ranked 2nd.
    assert [item.memory_id for item in fused] == [shared, fts_only, vector_only]
    assert fused[0].source == "vector"
    assert fused[0].score == pytest.approx(0.81)
    assert fused[1].source == "full_text"
    assert fused[1].score == pytest.approx(0.42)
    assert fused[2].source == "vector"
    assert fused[2].score == pytest.approx(0.64)
