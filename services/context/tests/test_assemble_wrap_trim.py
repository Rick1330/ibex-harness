"""Unit tests for wrap-aware packing / post-pack trim (F4-028)."""

from __future__ import annotations

from uuid import uuid4

ORG = uuid4()
AGENT = uuid4()


def _scored_memory(mid: str, content: str, score: float):
    from app.packer import ScoredMemory
    from app.retrieval import MemoryHit

    return ScoredMemory(
        hit=MemoryHit(
            memory_id=mid,
            org_id=str(ORG),
            agent_id=str(AGENT),
            content=content,
            category="factual",
            confidence=0.9,
            similarity=0.9,
            rank=1,
            source="vector",
        ),
        composite_score=score,
    )


def test_memory_wrap_reserve_edges() -> None:
    """F4-028: wrap reserve skips empty budget and scales with nonce size."""
    from app.assemble import _memory_wrap_delta, _memory_wrap_reserve
    from app.budget import representative_nonce
    from app.capability_catalog import default_catalog

    policy = default_catalog().family_policy("o200k_base")
    short_nonce = representative_nonce(16)
    long_nonce = representative_nonce(64)

    assert _memory_wrap_reserve([], 100, policy, nonce=short_nonce) == 0
    alone = [_scored_memory("m1", "hello", 0.9)]
    assert _memory_wrap_reserve(alone, 0, policy, nonce=short_nonce) == 0

    # Empty / zero-raw content still pays formatter wrapper tokens.
    empty = _scored_memory("empty-only", "", 1.0)
    assert _memory_wrap_delta(empty, policy, nonce=short_nonce, raw_tokens=0) > 0

    scored = [
        _scored_memory("empty", "", 1.0),
        _scored_memory("body", "x" * 80, 0.8),
        _scored_memory("too-big", "y" * 400, 0.5),
    ]
    short = _memory_wrap_reserve(scored, 30, policy, nonce=short_nonce)
    long = _memory_wrap_reserve(scored, 10_000, policy, nonce=long_nonce)
    assert short > 0
    assert long > short
    tiny = _memory_wrap_reserve(scored, 5, policy, nonce=short_nonce)
    assert 0 <= tiny <= short


def _wrap_trim_pair_fixture() -> tuple[object, ...]:
    """Shared keep/drop pair + costs for wrap-trim unit tests."""
    from app.budget import representative_nonce
    from app.capability_catalog import default_catalog
    from app.packer import PackedMemories

    policy = default_catalog().family_policy("o200k_base")
    nonce = representative_nonce(16)
    keep = _scored_memory("keep", "k" * 40, 0.95)
    drop = _scored_memory("drop", "d" * 40, 0.10)
    costs = {keep.memory_id: 32, drop.memory_id: 32}
    packed = PackedMemories(
        memories=(keep, drop),
        total_tokens=20,
        total_score=1.05,
        skipped_count=0,
        was_budget_reached=False,
        path="dp",
        candidates_evaluated=2,
        token_estimates={keep.memory_id: 10},
    )
    return policy, nonce, keep, drop, costs, packed


def test_trim_packed_for_wrap_drops_overflow() -> None:
    """Trim drops lowest-score memory and reports wrap-aware totals."""
    from app.assemble import _trim_packed_for_wrap, _WrapTrimInput

    policy, nonce, keep, drop, costs, packed = _wrap_trim_pair_fixture()
    trimmed = _trim_packed_for_wrap(
        _WrapTrimInput(
            packed=packed,
            scored=[keep, drop],
            usable_budget=40,
            policy=policy,
            nonce=nonce,
            cost_by_id=costs,
        )
    )
    assert len(trimmed.memories) == 1
    assert trimmed.memories[0].memory_id == keep.memory_id
    assert drop.memory_id in trimmed.budget_excluded_ids
    assert trimmed.was_budget_reached is True
    assert trimmed.total_tokens == costs[keep.memory_id]
    assert trimmed.skipped_count == 1


def test_trim_packed_for_wrap_skipped_count_no_double() -> None:
    """Packer-excluded IDs that stay excluded must not inflate skipped_count."""
    from app.assemble import _trim_packed_for_wrap, _WrapTrimInput
    from app.packer import PackedMemories

    policy, nonce, keep, drop, costs, _packed = _wrap_trim_pair_fixture()
    # Valid packer shape: keep selected, drop already budget-excluded.
    pre_excluded = PackedMemories(
        memories=(keep,),
        total_tokens=costs[keep.memory_id],
        total_score=keep.composite_score,
        skipped_count=1,
        was_budget_reached=True,
        path="dp",
        candidates_evaluated=2,
        budget_excluded_ids=frozenset({drop.memory_id}),
        token_estimates={keep.memory_id: 10, drop.memory_id: 10},
    )
    re_trimmed = _trim_packed_for_wrap(
        _WrapTrimInput(
            packed=pre_excluded,
            scored=[keep, drop],
            usable_budget=40,
            policy=policy,
            nonce=nonce,
            cost_by_id=costs,
        )
    )
    assert {m.memory_id for m in re_trimmed.memories} == {keep.memory_id}
    assert re_trimmed.skipped_count == 1
    assert re_trimmed.budget_excluded_ids == frozenset({drop.memory_id})
    assert re_trimmed.was_budget_reached is True
    assert re_trimmed.total_tokens == costs[keep.memory_id]


def test_trim_packed_for_wrap_refill_clears_restored_ids() -> None:
    """IDs dropped then restored by refill must leave exclusion metadata."""
    from app.assemble import _trim_packed_for_wrap, _WrapTrimInput
    from app.packer import PackedMemories

    policy, nonce, _keep, _drop, _costs, _packed = _wrap_trim_pair_fixture()
    # A+B over budget, A alone over, so both drop; refill restores A+C (not B).
    # C was dropped first (lowest score) then restored — must not stay excluded.
    a = _scored_memory("a", "a" * 40, 0.90)
    b = _scored_memory("b", "b" * 40, 0.50)
    c = _scored_memory("c", "c" * 40, 0.10)
    costs = {"a": 30, "b": 30, "c": 8}
    packed = PackedMemories(
        memories=(a, b, c),
        total_tokens=70,
        total_score=1.5,
        skipped_count=0,
        was_budget_reached=False,
        path="dp",
        candidates_evaluated=3,
        token_estimates={"a": 10, "b": 10, "c": 10},
    )
    # Budget fits A alone and A+C (with sep), but not A+B; C is dropped then restored.
    trimmed = _trim_packed_for_wrap(
        _WrapTrimInput(
            packed=packed,
            scored=[a, b, c],
            usable_budget=41,
            policy=policy,
            nonce=nonce,
            cost_by_id=costs,
        )
    )
    ids = {m.memory_id for m in trimmed.memories}
    assert ids == {"a", "c"}
    assert "c" not in trimmed.budget_excluded_ids
    assert trimmed.budget_excluded_ids == frozenset({"b"})
    assert trimmed.skipped_count == 1
    assert trimmed.was_budget_reached is True
    assert trimmed.total_tokens == costs["a"] + costs["c"]
    assert trimmed.token_estimates == {"a": 10, "b": 10, "c": 10}


def test_trim_packed_for_wrap_refill_recovers_packer_exclusions() -> None:
    """Refilling a packer-excluded ID removes it from budget_excluded_ids."""
    from app.assemble import _trim_packed_for_wrap, _WrapTrimInput
    from app.packer import PackedMemories

    policy, nonce, _k, _d, _c, _p = _wrap_trim_pair_fixture()
    high = _scored_memory("high", "H" * 40, 0.99)
    a = _scored_memory("a", "a" * 40, 0.40)
    b = _scored_memory("b", "b" * 40, 0.40)
    costs = {"high": 50, "a": 15, "b": 15}
    packed = PackedMemories(
        memories=(high,),
        total_tokens=50,
        total_score=0.99,
        skipped_count=2,
        was_budget_reached=True,
        path="dp",
        candidates_evaluated=3,
        budget_excluded_ids=frozenset({"a", "b"}),
        token_estimates={"high": 20, "a": 5, "b": 5},
    )
    fitted = _trim_packed_for_wrap(
        _WrapTrimInput(
            packed=packed,
            scored=[high, a, b],
            usable_budget=40,
            policy=policy,
            nonce=nonce,
            cost_by_id=costs,
        )
    )
    ids = {m.memory_id for m in fitted.memories}
    assert ids == {"a", "b"}
    assert fitted.budget_excluded_ids == frozenset({"high"})
    assert fitted.skipped_count == 1
    assert fitted.was_budget_reached is True
    assert fitted.total_tokens == costs["a"] + costs["b"]


def test_trim_packed_for_wrap_noop_and_selection_wrap() -> None:
    """No-op paths preserve identity; selection wrap counts without cost map."""
    from app.assemble import (
        _selection_raw_and_wrap,
        _trim_packed_for_wrap,
        _WrapCostContext,
        _WrapTrimInput,
    )

    policy, nonce, keep, drop, costs, packed = _wrap_trim_pair_fixture()
    assert (
        _trim_packed_for_wrap(
            _WrapTrimInput(
                packed=packed,
                scored=[keep, drop],
                usable_budget=10_000,
                policy=policy,
                nonce=nonce,
                cost_by_id=costs,
            )
        )
        is packed
    )
    assert (
        _trim_packed_for_wrap(
            _WrapTrimInput(
                packed=packed,
                scored=[keep, drop],
                usable_budget=0,
                policy=policy,
                nonce=nonce,
                cost_by_id=costs,
            )
        )
        is packed
    )
    raw_total, wrap_total = _selection_raw_and_wrap(
        [keep],
        _WrapCostContext(policy=policy, nonce=nonce, estimates={keep.memory_id: 10}),
    )
    assert raw_total == 10
    assert wrap_total > 0


def test_wrap_aware_pack_prefers_two_small_over_oversized_high_score() -> None:
    """High-score singleton that exceeds wrapped budget must not block two small fits."""
    from app.assemble import _trim_packed_for_wrap, _wrap_aware_costs, _WrapTrimInput
    from app.budget import representative_nonce
    from app.capability_catalog import default_catalog
    from app.packer import ContextPacker

    policy = default_catalog().family_policy("o200k_base")
    nonce = representative_nonce(16)
    # Raw sizes chosen so wrap makes the high-score item exceed budget alone,
    # while two lower-score items still fit together (including separator).
    high = _scored_memory("high", "H" * 200, 0.99)
    a = _scored_memory("a", "a" * 16, 0.40)
    b = _scored_memory("b", "b" * 16, 0.40)
    scored = [high, a, b]
    costs = _wrap_aware_costs(scored, policy, nonce=nonce)
    # Budget fits a+b with wraps+sep, but not high alone.
    budget = costs[a.memory_id] + costs[b.memory_id] + 2
    assert costs[high.memory_id] > budget
    assert costs[a.memory_id] + costs[b.memory_id] <= budget
    packer = ContextPacker(policy, bucket_size=16, dp_cell_ceiling=70 * 6251)
    packed = packer.pack(scored, budget, cost_by_id=costs)
    fitted = _trim_packed_for_wrap(
        _WrapTrimInput(
            packed=packed,
            scored=scored,
            usable_budget=budget,
            policy=policy,
            nonce=nonce,
            cost_by_id=costs,
        )
    )
    ids = {m.memory_id for m in fitted.memories}
    assert ids == {"a", "b"}
    assert "high" not in ids
    assert fitted.total_tokens == costs[a.memory_id] + costs[b.memory_id]
