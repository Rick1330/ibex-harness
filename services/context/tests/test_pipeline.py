"""Unit tests for pack_retrieval glue (milestone 3.5.C.4)."""

from __future__ import annotations

import unittest
from uuid import uuid4

from app.budget import TokenBudget
from app.capability_catalog import TokenizerFamilyPolicy
from app.estimate import ESTIMATE_CHARS_DIV_4
from app.packer import ContextPacker
from app.pipeline import pack_retrieval
from app.retrieval import BranchOutcome, MemoryHit, ResolvedDirective, RetrievalResult

ORG = uuid4()
AGENT = uuid4()
POLICY = TokenizerFamilyPolicy(ESTIMATE_CHARS_DIV_4, 0.02)


def _hit(
    *,
    memory_id: str,
    content: str,
    similarity: float,
    confidence: float = 0.8,
    rank: int = 1,
    source: str = "vector",
) -> MemoryHit:
    return MemoryHit(
        memory_id=memory_id,
        org_id=str(ORG),
        agent_id=str(AGENT),
        content=content,
        category="factual",
        confidence=confidence,
        similarity=similarity,
        rank=rank,
        source=source,
    )


def _budget(usable: int) -> TokenBudget:
    return TokenBudget(
        context_window=128_000,
        response_reserve=4096,
        safety_buffer=2560,
        usable_budget=usable,
        directive_tokens=10,
        messages_tokens=20,
        is_constrained=False,
        estimate_kind=ESTIMATE_CHARS_DIV_4,
    )


def _result(
    *,
    hot: list[MemoryHit] | None = None,
    cold: list[MemoryHit] | None = None,
) -> RetrievalResult:
    ok = BranchOutcome("success", 1.0)
    return RetrievalResult(
        directive=ResolvedDirective(content="be helpful", injection_mode="system_first", version_id=None),
        directive_outcome=ok,
        hot_memories=list(hot or []),
        hot_outcome=ok,
        cold_memories=list(cold or []),
        cold_outcome=ok,
        recent_messages=[],
        history_tokens=20,
        sources_available=frozenset({"directive", "hot", "cold"}),
    )


class PackRetrievalTests(unittest.TestCase):
    def test_dedupes_preferring_higher_interim_score(self) -> None:
        mid = str(uuid4())
        # Same id in hot (lower sim) and cold (higher sim).
        hot = [_hit(memory_id=mid, content="x" * 40, similarity=0.3, source="hot_cache")]
        cold = [_hit(memory_id=mid, content="x" * 40, similarity=0.9, source="vector")]
        packer = ContextPacker(POLICY)
        packed = pack_retrieval(_result(hot=hot, cold=cold), _budget(1000), packer=packer)
        self.assertEqual(len(packed.memories), 1)
        self.assertAlmostEqual(packed.memories[0].hit.similarity, 0.9)

    def test_respects_usable_budget(self) -> None:
        hits = [
            _hit(memory_id=str(uuid4()), content="y" * 400, similarity=0.8),
            _hit(memory_id=str(uuid4()), content="z" * 400, similarity=0.7),
        ]
        packer = ContextPacker(POLICY)
        packed = pack_retrieval(_result(hot=hits), _budget(50), packer=packer)
        self.assertLessEqual(packed.total_tokens, 50)


if __name__ == "__main__":
    unittest.main()
