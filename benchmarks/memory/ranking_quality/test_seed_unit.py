"""Unit tests for the seed path's pure pieces (the async seeding is integration-tested)."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

_RANK_DIR = Path(__file__).resolve().parent
_MEMORY_DIR = _RANK_DIR.parents[2] / "services" / "memory"
for _path in (_MEMORY_DIR, _RANK_DIR.parent, _RANK_DIR):
    if str(_path) not in sys.path:
        sys.path.insert(0, str(_path))

import seed
from profiles import profile_cosine


class TestEmbeddingForRow:
    def test_v1_row_returns_none(self) -> None:
        row = {"content_key": "gold.x", "embedding_hotspot": 3}

        assert seed._embedding_for_row(row, None) is None

    def test_v2_row_returns_the_profile_vector(self) -> None:
        topics = {"a": 0, "b": 1}
        row = {"content_key": "gold.x", "embedding_profile": {"a": 0.6, "b": 0.8}}

        vector = seed._embedding_for_row(row, topics)

        assert vector is not None
        assert vector[0] == pytest.approx(0.6)
        assert vector[1] == pytest.approx(0.8)

    def test_v2_row_without_topics_is_rejected(self) -> None:
        row = {"content_key": "gold.x", "embedding_profile": {"a": 1.0}}

        with pytest.raises(ValueError, match="declares no topics"):
            seed._embedding_for_row(row, None)

    def test_stored_vector_reproduces_the_validator_cosine(self) -> None:
        # The corpus design says cos(query, memory) is the weight; the seeded vector is what
        # pgvector will actually score, so the two must agree.
        topics = {"a": 0, "b": 1}
        left = seed._embedding_for_row({"content_key": "l", "embedding_profile": {"a": 0.8, "b": 0.6}}, topics)
        right = seed._embedding_for_row({"content_key": "r", "embedding_profile": {"a": 0.6, "b": 0.8}}, topics)

        dot = sum(x * y for x, y in zip(left, right, strict=True))
        assert dot == pytest.approx(profile_cosine({"a": 0.8, "b": 0.6}, {"a": 0.6, "b": 0.8}))


class TestConflictPairs:
    def test_pairs_are_winner_then_twin(self) -> None:
        memories = [
            {"content_key": "gold.current.0", "conflicts_with": ["gold.twin.0"]},
            {"content_key": "gold.twin.0"},
        ]

        assert seed._conflict_pairs(memories) == [("gold.current.0", "gold.twin.0")]

    def test_no_conflicts_yields_no_pairs(self) -> None:
        assert seed._conflict_pairs([{"content_key": "gold.a"}]) == []
