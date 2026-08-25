"""Weighted composite score (relevance / recency / usefulness / confidence / frequency)."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

from app.scoring.half_life import recency_decay


@dataclass(frozen=True, slots=True)
class RankWeights:
    relevance: float = 0.40
    recency: float = 0.25
    usefulness: float = 0.20
    confidence: float = 0.10
    frequency: float = 0.05

    def validate(self) -> None:
        total = (
            self.relevance
            + self.recency
            + self.usefulness
            + self.confidence
            + self.frequency
        )
        if abs(total - 1.0) > 1e-9:
            msg = f"rank weights must sum to 1.0, got {total}"
            raise ValueError(msg)


def score(
    *,
    relevance: float,
    recency: float,
    usefulness: float,
    confidence: float,
    access_frequency: float,
    weights: RankWeights | None = None,
) -> float:
    """Pure weighted sum. Callers supply precomputed component scores in [0, 1]."""
    w = weights or RankWeights()
    w.validate()
    return (
        w.relevance * relevance
        + w.recency * recency
        + w.usefulness * usefulness
        + w.confidence * confidence
        + w.frequency * access_frequency
    )


def composite_score(
    *,
    relevance: float,
    age_days: float,
    categories: Sequence[str],
    usefulness: float,
    confidence: float,
    access_frequency: float,
    weights: RankWeights | None = None,
) -> float:
    """Composite score with category-conditional recency decay."""
    return score(
        relevance=relevance,
        recency=recency_decay(age_days, categories),
        usefulness=usefulness,
        confidence=confidence,
        access_frequency=access_frequency,
        weights=weights,
    )
