"""Unit tests for ContextPacker (milestone 3.5.C.4)."""

from __future__ import annotations

import random
import unittest
from dataclasses import dataclass
from uuid import uuid4

from app.capability_catalog import TokenizerFamilyPolicy
from app.estimate import ESTIMATE_CHARS_DIV_4, estimate_tokens
from app.packer import BUCKET_SIZE, ContextPacker, ScoredMemory, _FinalizeArgs
from app.retrieval import MemoryHit

ORG = str(uuid4())
AGENT = str(uuid4())
POLICY = TokenizerFamilyPolicy(ESTIMATE_CHARS_DIV_4, 0.02)


@dataclass(frozen=True, slots=True)
class _HitSeed:
    content: str
    similarity: float = 0.8
    confidence: float = 0.8
    rank: int = 1
    memory_id: str | None = None
    category: str = "factual"


def _hit(seed: _HitSeed) -> MemoryHit:
    return MemoryHit(
        memory_id=seed.memory_id or str(uuid4()),
        org_id=ORG,
        agent_id=AGENT,
        content=seed.content,
        category=seed.category,
        confidence=seed.confidence,
        similarity=seed.similarity,
        rank=seed.rank,
        source="vector",
    )


def _scored(
    content: str,
    score: float,
    *,
    memory_id: str | None = None,
) -> ScoredMemory:
    return ScoredMemory(
        hit=_hit(_HitSeed(content=content, memory_id=memory_id)),
        composite_score=score,
    )


def _content_for_tokens(token_target: int) -> str:
    if token_target <= 0:
        return ""
    return "x" * (4 * token_target)


def _packer(**kwargs: object) -> ContextPacker:
    return ContextPacker(POLICY, **kwargs)  # type: ignore[arg-type]


def _exact_best_score(items: list[ScoredMemory], tokens: list[int], budget: int) -> float:
    best = 0.0
    n = len(items)
    for mask in range(1 << n):
        total_t = 0
        total_s = 0.0
        for i in range(n):
            if mask & (1 << i):
                total_t += tokens[i]
                total_s += items[i].composite_score
        if total_t <= budget and total_s > best:
            best = total_s
    return best


class PackerEdgeTests(unittest.TestCase):
    def test_empty_candidates(self) -> None:
        packed = _packer().pack([], 1000)
        self.assertEqual(packed.memories, ())
        self.assertEqual(packed.skipped_count, 0)
        self.assertFalse(packed.was_budget_reached)
        self.assertEqual(packed.path, "dp")

    def test_non_positive_budget(self) -> None:
        items = [_scored(_content_for_tokens(10), 1.0)]
        packed = _packer().pack(items, 0)
        self.assertEqual(len(packed.memories), 0)
        self.assertEqual(packed.skipped_count, 1)
        self.assertTrue(packed.was_budget_reached)

    def test_single_item_too_large(self) -> None:
        items = [_scored(_content_for_tokens(100), 1.0)]
        packed = _packer().pack(items, 50)
        self.assertEqual(len(packed.memories), 0)
        self.assertEqual(packed.skipped_count, 1)
        self.assertTrue(packed.was_budget_reached)

    def test_single_item_exact_fill(self) -> None:
        items = [_scored(_content_for_tokens(40), 0.9)]
        packed = _packer().pack(items, 40)
        self.assertEqual(len(packed.memories), 1)
        self.assertEqual(packed.total_tokens, 40)
        self.assertFalse(packed.was_budget_reached)

    def test_all_identical_fit(self) -> None:
        items = [
            _scored(_content_for_tokens(BUCKET_SIZE), 0.5, memory_id=str(uuid4()))
            for _ in range(5)
        ]
        packed = _packer().pack(items, 5 * BUCKET_SIZE)
        self.assertEqual(len(packed.memories), 5)
        self.assertFalse(packed.was_budget_reached)

    def test_all_too_large(self) -> None:
        items = [_scored(_content_for_tokens(80), 0.5) for _ in range(4)]
        packed = _packer().pack(items, 50)
        self.assertEqual(len(packed.memories), 0)
        self.assertEqual(packed.skipped_count, 4)
        self.assertTrue(packed.was_budget_reached)

    def test_ordering_score_desc_then_id(self) -> None:
        low = _scored(
            _content_for_tokens(5),
            0.2,
            memory_id="aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa",
        )
        high = _scored(
            _content_for_tokens(5),
            0.9,
            memory_id="bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb",
        )
        mid = _scored(
            _content_for_tokens(5),
            0.5,
            memory_id="cccccccc-cccc-cccc-cccc-cccccccccccc",
        )
        packed = _packer().pack([low, high, mid], 100)
        scores = [m.composite_score for m in packed.memories]
        self.assertEqual(scores, sorted(scores, reverse=True))
        self.assertEqual(packed.memories[0].memory_id, high.memory_id)


class PackerCorrectnessTests(unittest.TestCase):
    def test_dp_matches_brute_force_when_tokens_align_to_buckets(self) -> None:
        """When token sizes are multiples of BUCKET_SIZE, bucket DP ≡ exact 0/1."""
        rng = random.Random(42)
        packer = _packer()
        for _ in range(40):
            n = rng.randint(1, 12)
            # Budget multiple of bucket size so capacity aligns.
            buckets = rng.randint(2, 20)
            budget = buckets * BUCKET_SIZE
            items: list[ScoredMemory] = []
            tokens: list[int] = []
            for _i in range(n):
                w = rng.randint(1, max(1, buckets // 2))
                t = w * BUCKET_SIZE
                tokens.append(t)
                items.append(_scored(_content_for_tokens(t), rng.random()))
            packed = packer.pack(items, budget)
            self.assertLessEqual(packed.total_tokens, budget)
            self.assertAlmostEqual(
                packed.total_score,
                _exact_best_score(items, tokens, budget),
                places=9,
            )

    def test_invariants_seeded(self) -> None:
        rng = random.Random(7)
        packer = _packer()
        for _ in range(30):
            n = rng.randint(0, 20)
            budget = rng.randint(0, 300)
            items = [
                _scored(_content_for_tokens(rng.randint(1, 50)), rng.random()) for _ in range(n)
            ]
            packed = packer.pack(items, budget)
            if budget <= 0:
                self.assertEqual(len(packed.memories), 0)
                self.assertEqual(packed.total_tokens, 0)
            else:
                self.assertLessEqual(packed.total_tokens, budget)
            self.assertEqual(packed.skipped_count + len(packed.memories), n)
            self.assertAlmostEqual(
                packed.total_score,
                sum(m.composite_score for m in packed.memories),
                places=9,
            )
            self.assertEqual(packed.candidates_evaluated, n)


class PackerAdversarialTests(unittest.TestCase):
    def test_dp_beats_greedy_on_stranded_budget(self) -> None:
        """Large high-score item strands remainder; smaller items fill via DP.

        After taking the large item (~60% budget), each smaller item exceeds the
        remainder, so greedy consecutive-skips stop near 60% utilization. DP
        packs two medium items instead (~100%).
        """
        budget = 1000
        large = _scored(_content_for_tokens(600), 0.95, memory_id="large")
        # Each medium exceeds the 400 remainder after taking large.
        mediums = [
            _scored(_content_for_tokens(500), 0.55, memory_id=f"med-{i:02d}") for i in range(15)
        ]
        items = [large, *mediums]
        packer = _packer(max_consecutive_skips=5)
        dp = packer.pack(items, budget)
        greedy = packer.pack_greedy_only(items, budget)

        dp_util = dp.total_tokens / budget
        greedy_util = greedy.total_tokens / budget
        self.assertGreaterEqual(dp_util, 0.90)
        self.assertLess(greedy_util, 0.65)
        self.assertEqual(dp.path, "dp")
        self.assertEqual(greedy.path, "greedy")
        self.assertGreater(dp.total_score, greedy.total_score)


class PackerFallbackTests(unittest.TestCase):
    def test_pathological_ceiling_uses_greedy(self) -> None:
        items = [_scored(_content_for_tokens(10), 0.5) for _ in range(8)]
        packer = _packer(dp_cell_ceiling=1)
        packed = packer.pack(items, 200)
        self.assertEqual(packed.path, "greedy")
        self.assertLessEqual(packed.total_tokens, 200)
        self.assertEqual(packed.skipped_count + len(packed.memories), 8)

    def test_was_budget_reached_when_truncated(self) -> None:
        items = [_scored(_content_for_tokens(40), 0.5) for _ in range(5)]
        packed = _packer().pack(items, 100)
        self.assertTrue(packed.was_budget_reached)
        self.assertGreater(packed.skipped_count, 0)

    def test_was_budget_reached_false_when_all_fit(self) -> None:
        items = [_scored(_content_for_tokens(10), 0.5) for _ in range(3)]
        packed = _packer().pack(items, 100)
        self.assertFalse(packed.was_budget_reached)
        self.assertEqual(packed.skipped_count, 0)

    def test_ctor_rejects_invalid(self) -> None:
        with self.assertRaises(ValueError):
            _packer(bucket_size=0)
        with self.assertRaises(ValueError):
            _packer(dp_cell_ceiling=0)
        with self.assertRaises(ValueError):
            _packer(max_consecutive_skips=-1)

    def test_zero_weight_empty_content_included(self) -> None:
        empty = _scored("", 0.8, memory_id="empty")
        other = _scored(_content_for_tokens(16), 0.5, memory_id="other")
        packed = _packer().pack([empty, other], 16)
        ids = {m.memory_id for m in packed.memories}
        self.assertIn("empty", ids)

    def test_greedy_only_empty_and_zero_budget(self) -> None:
        empty = _packer().pack_greedy_only([], 100)
        self.assertEqual(empty.path, "greedy")
        self.assertEqual(empty.skipped_count, 0)
        items = [_scored(_content_for_tokens(10), 0.5)]
        zero = _packer().pack_greedy_only(items, 0)
        self.assertEqual(zero.skipped_count, 1)
        self.assertTrue(zero.was_budget_reached)

    def test_scored_memory_properties(self) -> None:
        item = _scored(_content_for_tokens(4), 0.7, memory_id="prop-id")
        self.assertEqual(item.memory_id, "prop-id")
        self.assertEqual(item.content, _content_for_tokens(4))
        self.assertEqual(item.category, "factual")


    def test_finalize_raises_when_tokens_exceed_budget(self) -> None:
        item = _scored(_content_for_tokens(40), 0.5)
        packer = _packer()
        with self.assertRaises(RuntimeError):
            packer._finalize(
                _FinalizeArgs(
                    candidates=[item],
                    selected=[0],
                    tokens=[100],
                    token_budget=50,
                    path="dp",
                )
            )


class PackerDeterminismAndRepairTests(unittest.TestCase):
    def test_default_ceiling_allows_n70_at_100k_budget(self) -> None:
        from app.config import ContextSettings
        from app.packer import DEFAULT_DP_CELL_CEILING

        n = 70
        buckets = 100_000 // BUCKET_SIZE  # 6250
        cells = n * (buckets + 1)
        self.assertEqual(DEFAULT_DP_CELL_CEILING, 70 * 6251)
        self.assertEqual(ContextSettings().packer_dp_cell_ceiling, DEFAULT_DP_CELL_CEILING)
        self.assertLessEqual(cells, ContextSettings().packer_dp_cell_ceiling)

        items = [
            _scored(_content_for_tokens(16), 0.5 + (i % 10) * 0.01, memory_id=f"id-{i:03d}")
            for i in range(n)
        ]
        packed = _packer().pack(items, 100_000)
        self.assertEqual(packed.path, "dp")

    def test_equal_score_selection_stable_under_input_reversal(self) -> None:
        a = _scored(_content_for_tokens(16), 0.5, memory_id="aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa")
        b = _scored(_content_for_tokens(16), 0.5, memory_id="bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb")
        # Budget fits exactly one of the equal-score items.
        forward = _packer().pack([a, b], 16)
        reverse = _packer().pack([b, a], 16)
        self.assertEqual(
            {m.memory_id for m in forward.memories},
            {m.memory_id for m in reverse.memories},
        )
        self.assertEqual(len(forward.memories), 1)
        self.assertEqual(forward.memories[0].memory_id, a.memory_id)

    def test_repair_refills_after_dropping_oversize_bucket_pick(self) -> None:
        """DP may pick a 31-token item (bucket weight 1) under a 16-token budget.

        Repair must drop it and refill with the previously rejected exact fit.
        """
        oversized = _scored(_content_for_tokens(31), 0.95, memory_id="oversize")
        exact = _scored(_content_for_tokens(16), 0.40, memory_id="exact-fit")
        packed = _packer().pack([oversized, exact], 16)
        self.assertEqual(packed.path, "dp")
        self.assertEqual([m.memory_id for m in packed.memories], ["exact-fit"])
        self.assertEqual(packed.total_tokens, 16)


class PackerTokenHelperTests(unittest.TestCase):
    def test_estimate_matches_content_helper(self) -> None:
        text = _content_for_tokens(17)
        tokens, kind = estimate_tokens(text, POLICY)
        self.assertEqual(kind, ESTIMATE_CHARS_DIV_4)
        self.assertEqual(tokens, 17)


if __name__ == "__main__":
    unittest.main()
