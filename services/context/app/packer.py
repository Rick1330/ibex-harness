"""Bounded DP knapsack memory packer (milestone 3.5.C.4 / ADR-0069).

Selects a subset of scored memories under a token budget. Default path is a
bucketed 0/1 knapsack DP vectorized with numpy. When ``n * buckets`` exceeds a
safety ceiling, falls back to score-descending greedy with a consecutive-skip
limit.

Packed output is ordered by descending interim ``composite_score``, then
``memory_id`` for ties (deterministic; not input order).
"""

from __future__ import annotations

import logging
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Final, Literal

import numpy as np

from app.capability_catalog import TokenizerFamilyPolicy
from app.estimate import estimate_tokens
from app.retrieval import MemoryHit

logger = logging.getLogger(__name__)

BUCKET_SIZE: Final[int] = 16
# Default ceiling: n=70 × (buckets+1) for ~100k-token budget / 16 → buckets=6250.
DEFAULT_DP_CELL_CEILING: Final[int] = 70 * 6251
DEFAULT_MAX_CONSECUTIVE_SKIPS: Final[int] = 5

PackPath = Literal["dp", "greedy"]


@dataclass(frozen=True, slots=True)
class ScoredMemory:
    """One packing candidate: a retrieval hit plus its interim packer score.

    ``composite_score`` is the *interim* context-local score from ``app.scoring``
    (``0.85×similarity + 0.15×confidence``). It is **not** the memory-service
    ``composite_score`` (recency / usefulness / frequency) until that value is
    exposed on the HTTP search/hot wire.
    """

    hit: MemoryHit
    composite_score: float

    @property
    def memory_id(self) -> str:
        """Stable memory UUID from the underlying hit."""
        return self.hit.memory_id

    @property
    def content(self) -> str:
        """Raw memory body text used for token estimation and formatting."""
        return self.hit.content

    @property
    def category(self) -> str:
        """Memory category label (e.g. factual / episodic) from the hit."""
        return self.hit.category


@dataclass(frozen=True, slots=True)
class PackedMemories:
    """Subset selected under a token budget for the formatter / future metrics.

    Handed to ``ContextFormatter`` (3.5.C.5) and eventually ``AssemblyMetrics``
    / ``AssembleContextResponse`` (3.5.C.6). ``path`` records whether the DP
    knapsack or the greedy fallback ran. ``was_budget_reached`` is True when at
    least one candidate was excluded because it would not fit the budget
    (including a non-positive budget with candidates present).
    """

    memories: tuple[ScoredMemory, ...]
    total_tokens: int
    total_score: float
    skipped_count: int
    was_budget_reached: bool
    path: PackPath
    candidates_evaluated: int


@dataclass(frozen=True, slots=True)
class _FinalizeArgs:
    candidates: list[ScoredMemory]
    selected: list[int]
    tokens: list[int]
    token_budget: int
    path: PackPath


@dataclass(frozen=True, slots=True)
class _RepairArgs:
    selected: list[int]
    candidates: list[ScoredMemory]
    tokens: list[int]
    token_budget: int
    values: list[float]


class ContextPacker:
    """Select a score-maximizing memory subset under a token budget (ADR-0069).

    Default path: numpy-vectorized bucketed 0/1 knapsack (bucket size 16) with
    exact-token repair after DP. When ``n * (buckets+1)`` exceeds
    ``dp_cell_ceiling``, falls back to score-descending greedy with a
    consecutive-skip limit so pathological table sizes cannot blow latency.
    """

    def __init__(
        self,
        policy: TokenizerFamilyPolicy,
        *,
        bucket_size: int = BUCKET_SIZE,
        dp_cell_ceiling: int = DEFAULT_DP_CELL_CEILING,
        max_consecutive_skips: int = DEFAULT_MAX_CONSECUTIVE_SKIPS,
    ) -> None:
        """Validate knobs and bind the tokenizer policy used for estimates."""
        if bucket_size < 1:
            msg = f"bucket_size must be >= 1, got {bucket_size}"
            raise ValueError(msg)
        if dp_cell_ceiling < 1:
            msg = f"dp_cell_ceiling must be >= 1, got {dp_cell_ceiling}"
            raise ValueError(msg)
        if max_consecutive_skips < 0:
            msg = f"max_consecutive_skips must be >= 0, got {max_consecutive_skips}"
            raise ValueError(msg)
        self._policy = policy
        self._bucket_size = bucket_size
        self._dp_cell_ceiling = dp_cell_ceiling
        self._max_consecutive_skips = max_consecutive_skips

    def pack(
        self,
        scored: Sequence[ScoredMemory],
        token_budget: int,
    ) -> PackedMemories:
        """Select memories under ``token_budget`` using DP or greedy fallback.

        Semantics for ``was_budget_reached``:

        - Empty candidate list → empty pack, ``was_budget_reached=False``
          (nothing was truncated).
        - ``token_budget <= 0`` with one or more candidates → empty pack,
          ``was_budget_reached=True`` (budget exhausted / unusable; every
          candidate is excluded for budget reasons). Zero and negative share
          this branch so bucket math never sees a non-positive capacity.
        - Positive budget that excludes at least one candidate → ``True``.
        - Positive budget that fits every candidate → ``False``.

        Candidates are sorted by descending score then ``memory_id`` before DP
        so equal-score ties are independent of caller input order.
        """
        # Canonical order: equal scores resolve the same regardless of input order.
        candidates = sorted(
            scored,
            key=lambda item: (-item.composite_score, item.memory_id),
        )
        n = len(candidates)
        if n == 0:
            return _empty_pack(path="dp", skipped=0, evaluated=0)
        if token_budget <= 0:
            return _empty_pack(path="dp", skipped=n, evaluated=n, was_budget_reached=True)

        tokens = [self._tokens(item) for item in candidates]
        buckets = max(1, token_budget // self._bucket_size)
        weights = [_bucket_weight(t, self._bucket_size) for t in tokens]
        values = [float(item.composite_score) for item in candidates]

        cells = n * (buckets + 1)
        if cells > self._dp_cell_ceiling:
            logger.warning(
                "packer_dp_ceiling_exceeded falling_back_to_greedy "
                "n=%s buckets=%s cells=%s ceiling=%s",
                n,
                buckets,
                cells,
                self._dp_cell_ceiling,
            )
            selected = self._greedy_select(candidates, tokens, token_budget)
            path: PackPath = "greedy"
        else:
            selected = _dp_select(weights, values, buckets)
            selected = self._repair_exact_budget(
                _RepairArgs(
                    selected=selected,
                    candidates=candidates,
                    tokens=tokens,
                    token_budget=token_budget,
                    values=values,
                )
            )
            path = "dp"
        return self._finalize(
            _FinalizeArgs(
                candidates=candidates,
                selected=selected,
                tokens=tokens,
                token_budget=token_budget,
                path=path,
            )
        )

    def pack_greedy_only(
        self,
        scored: Sequence[ScoredMemory],
        token_budget: int,
    ) -> PackedMemories:
        """Run only the greedy path (tests / adversarial baselines).

        Same ``was_budget_reached`` semantics as :meth:`pack` for empty input
        and ``token_budget <= 0``. Always sets ``path="greedy"``.
        """
        candidates = list(scored)
        n = len(candidates)
        if n == 0:
            return _empty_pack(path="greedy", skipped=0, evaluated=0)
        if token_budget <= 0:
            return _empty_pack(path="greedy", skipped=n, evaluated=n, was_budget_reached=True)
        tokens = [self._tokens(item) for item in candidates]
        selected = self._greedy_select(candidates, tokens, token_budget)
        return self._finalize(
            _FinalizeArgs(
                candidates=candidates,
                selected=selected,
                tokens=tokens,
                token_budget=token_budget,
                path="greedy",
            )
        )

    def _tokens(self, item: ScoredMemory) -> int:
        count, _kind = estimate_tokens(item.content, self._policy)
        return int(count)

    def _greedy_select(
        self,
        candidates: list[ScoredMemory],
        tokens: list[int],
        token_budget: int,
    ) -> list[int]:
        order = sorted(
            range(len(candidates)),
            key=lambda i: (-candidates[i].composite_score, candidates[i].memory_id),
        )
        selected: list[int] = []
        used = 0
        consecutive_skips = 0
        for idx in order:
            cost = tokens[idx]
            if cost <= token_budget - used:
                selected.append(idx)
                used += cost
                consecutive_skips = 0
                continue
            consecutive_skips += 1
            if consecutive_skips > self._max_consecutive_skips:
                break
        return selected

    def _repair_exact_budget(self, args: _RepairArgs) -> list[int]:
        """Drop over-budget picks, then refill freed capacity from rejects."""
        chosen = list(args.selected)
        tokens = args.tokens
        values = args.values
        candidates = args.candidates
        token_budget = args.token_budget
        while chosen and sum(tokens[i] for i in chosen) > token_budget:
            drop_at = min(
                range(len(chosen)),
                key=lambda j: (values[chosen[j]], candidates[chosen[j]].memory_id),
            )
            chosen.pop(drop_at)

        used = sum(tokens[i] for i in chosen)
        chosen_set = set(chosen)
        for idx in sorted(
            range(len(candidates)),
            key=lambda i: (-values[i], candidates[i].memory_id),
        ):
            if idx in chosen_set:
                continue
            cost = tokens[idx]
            if cost <= token_budget - used:
                chosen.append(idx)
                chosen_set.add(idx)
                used += cost
        return chosen

    def _finalize(self, args: _FinalizeArgs) -> PackedMemories:
        packed = [args.candidates[i] for i in args.selected]
        packed.sort(key=lambda m: (-m.composite_score, m.memory_id))
        total_tokens = sum(args.tokens[i] for i in args.selected)
        total_score = sum(m.composite_score for m in packed)
        skipped = len(args.candidates) - len(packed)
        was_budget_reached = skipped > 0
        if total_tokens > args.token_budget:
            msg = (
                f"internal packer bug: tokens {total_tokens} > budget {args.token_budget}"
            )
            raise RuntimeError(msg)
        return PackedMemories(
            memories=tuple(packed),
            total_tokens=total_tokens,
            total_score=total_score,
            skipped_count=skipped,
            was_budget_reached=was_budget_reached,
            path=args.path,
            candidates_evaluated=len(args.candidates),
        )


def _empty_pack(
    *,
    path: PackPath,
    skipped: int,
    evaluated: int,
    was_budget_reached: bool = False,
) -> PackedMemories:
    return PackedMemories(
        memories=(),
        total_tokens=0,
        total_score=0.0,
        skipped_count=skipped,
        was_budget_reached=was_budget_reached,
        path=path,
        candidates_evaluated=evaluated,
    )


def _dp_select(
    weights: list[int],
    values: list[float],
    buckets: int,
) -> list[int]:
    n = len(weights)
    prev = np.zeros(buckets + 1, dtype=np.float64)
    keep = np.zeros((n + 1, buckets + 1), dtype=bool)
    for i, (w, v) in enumerate(zip(weights, values, strict=True), start=1):
        prev, keep[i] = _dp_row(prev, w, v, buckets)
    return _dp_backtrack(keep, weights, buckets)


def _dp_row(
    prev: np.ndarray,
    weight: int,
    value: float,
    buckets: int,
) -> tuple[np.ndarray, np.ndarray]:
    """Compute one DP item row and its keep flags."""
    curr = prev.copy()
    keep_row = np.zeros(buckets + 1, dtype=bool)
    if weight == 0:
        better = (prev + value) > prev
        return np.where(better, prev + value, prev), better
    if weight > buckets:
        return curr, keep_row
    take = prev[: buckets + 1 - weight] + value
    skip = prev[weight:]
    better = take > skip
    curr[weight:] = np.where(better, take, skip)
    keep_row[weight:] = better
    return curr, keep_row


def _dp_backtrack(keep: np.ndarray, weights: list[int], buckets: int) -> list[int]:
    selected: list[int] = []
    capacity = buckets
    for i in range(len(weights), 0, -1):
        if not keep[i, capacity]:
            continue
        selected.append(i - 1)
        capacity -= weights[i - 1]
    selected.reverse()
    return selected


def _bucket_weight(token_count: int, bucket_size: int) -> int:
    if token_count <= 0:
        return 0
    return max(1, token_count // bucket_size)
