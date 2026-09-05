"""Unit tests for interim packer scoring (milestone 3.5.C.4)."""

from __future__ import annotations

import unittest
from uuid import uuid4

from app.retrieval import MemoryHit
from app.scoring import score_hits, score_memory_hit


def _hit(*, similarity: float, confidence: float) -> MemoryHit:
    return MemoryHit(
        memory_id=str(uuid4()),
        org_id=str(uuid4()),
        agent_id=str(uuid4()),
        content="prefers dark mode",
        category="preference",
        confidence=confidence,
        similarity=similarity,
        rank=1,
        source="vector",
    )


class InterimScoreTests(unittest.TestCase):
    def test_weighted_sum(self) -> None:
        hit = _hit(similarity=1.0, confidence=0.0)
        self.assertAlmostEqual(score_memory_hit(hit), 0.85)

    def test_bounds(self) -> None:
        hit = _hit(similarity=0.5, confidence=0.5)
        score = score_memory_hit(hit)
        self.assertGreaterEqual(score, 0.0)
        self.assertLessEqual(score, 1.0)

    def test_rejects_out_of_range(self) -> None:
        with self.assertRaises(ValueError):
            score_memory_hit(_hit(similarity=1.5, confidence=0.5))

    def test_rejects_non_finite(self) -> None:
        with self.assertRaises(ValueError):
            score_memory_hit(_hit(similarity=float("nan"), confidence=0.5))

    def test_rejects_bool(self) -> None:
        hit = _hit(similarity=0.5, confidence=0.5)
        object.__setattr__(hit, "similarity", True)  # type: ignore[misc]
        # MemoryHit is frozen — construct via replace of bad values differently:
        with self.assertRaises(TypeError):
            from app.scoring import _require_unit

            _require_unit("similarity", True)  # type: ignore[arg-type]

    def test_score_hits_wraps(self) -> None:
        hits = [_hit(similarity=0.8, confidence=0.6), _hit(similarity=0.2, confidence=0.9)]
        scored = score_hits(hits)
        self.assertEqual(len(scored), 2)
        self.assertAlmostEqual(scored[0].composite_score, score_memory_hit(hits[0]))


if __name__ == "__main__":
    unittest.main()
