"""Ranking-quality metrics for gold-set evaluation (precision@k, recall@k, MRR)."""

from __future__ import annotations

from typing import Sequence


def precision_at_k(ranked: Sequence[str], expected: Sequence[str], k: int) -> float:
    """Fraction of top-k retrieved IDs that appear in the relevance set."""
    if k < 1:
        msg = "k must be >= 1"
        raise ValueError(msg)
    if not expected:
        return 0.0
    top = ranked[:k]
    if not top:
        return 0.0
    expected_set = set(expected)
    hits = sum(1 for item in top if item in expected_set)
    return hits / min(k, len(top))


def recall_at_k(ranked: Sequence[str], expected: Sequence[str], k: int) -> float:
    """Fraction of expected IDs found within top-k."""
    if k < 1:
        msg = "k must be >= 1"
        raise ValueError(msg)
    if not expected:
        return 0.0
    expected_set = set(expected)
    top = ranked[:k]
    hits = sum(1 for item in expected_set if item in top)
    return hits / len(expected_set)


def mean_reciprocal_rank(ranked: Sequence[str], expected: Sequence[str]) -> float:
    """Reciprocal rank of the first expected hit (0 when none)."""
    if not expected:
        return 0.0
    expected_set = set(expected)
    for index, item in enumerate(ranked, start=1):
        if item in expected_set:
            return 1.0 / index
    return 0.0


def macro_mean(values: Sequence[float]) -> float:
    if not values:
        return 0.0
    return sum(values) / len(values)
