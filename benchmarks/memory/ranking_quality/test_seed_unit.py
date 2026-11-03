"""Unit tests for the seed path's pure pieces (the async seeding is integration-tested)."""

from __future__ import annotations

import sys
from datetime import UTC, datetime
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

class TestStoredVector:
    @pytest.mark.asyncio
    async def test_v2_row_passes_the_profile_vector_to_the_store(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """What the store is asked to persist, not just what the helper returns."""
        from uuid import UUID

        captured: dict[str, object] = {}

        async def fake_insert(*args: object, **kwargs: object) -> UUID:
            return UUID("11111111-2222-3333-4444-555555555555")

        async def fake_upsert(store: object, session_factory: object, **kwargs: object) -> list[float]:
            captured.update(kwargs)
            return []

        monkeypatch.setattr(seed, "insert_scored_memory", fake_insert)
        monkeypatch.setattr(seed, "upsert_embedding", fake_upsert)
        ctx = seed.SeedContext(
            session_factory=object(),  # type: ignore[arg-type]
            store=object(),  # type: ignore[arg-type]
            topics={"a": 0, "b": 1},
            now=datetime.now(tz=UTC),
        )
        row = {
            "content_key": "gold.x",
            "content": "A statement long enough to pass any length check.",
            "category": "factual",
            "embedding_profile": {"a": 0.6, "b": 0.8},
        }

        await seed._seed_memory_row(ctx, row)

        vector = captured["embedding"]
        assert vector[0] == pytest.approx(0.6)  # type: ignore[index]
        assert vector[1] == pytest.approx(0.8)  # type: ignore[index]
        # The stored vector is the sparse profile, not a one-hot hotspot.
        assert sum(1 for value in vector if value != 0.0) == 2  # type: ignore[union-attr]
        assert captured["hotspot"] == 0
