"""Weighted composite score (relevance / recency / usefulness / confidence / frequency)."""

from __future__ import annotations

import math
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
        for name, value in (
            ("relevance", self.relevance),
            ("recency", self.recency),
            ("usefulness", self.usefulness),
            ("confidence", self.confidence),
            ("frequency", self.frequency),
        ):
            _require_unit_interval(name, value)
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


@dataclass(frozen=True, slots=True)
class ScoreComponents:
    """Precomputed [0, 1] component scores for a weighted sum."""

    relevance: float
    recency: float
    usefulness: float
    confidence: float
    access_frequency: float


@dataclass(frozen=True, slots=True)
class CompositeInputs:
    """Inputs for category-conditional composite scoring."""

    relevance: float
    age_days: float
    categories: Sequence[str]
    usefulness: float
    confidence: float
    access_frequency: float


def score(
    components: ScoreComponents,
    weights: RankWeights | None = None,
) -> float:
    """Pure weighted sum. Callers supply precomputed component scores in [0, 1]."""
    for name, value in (
        ("relevance", components.relevance),
        ("recency", components.recency),
        ("usefulness", components.usefulness),
        ("confidence", components.confidence),
        ("access_frequency", components.access_frequency),
    ):
        _require_unit_interval(name, value)
    w = weights or RankWeights()
    w.validate()
    return (
        w.relevance * components.relevance
        + w.recency * components.recency
        + w.usefulness * components.usefulness
        + w.confidence * components.confidence
        + w.frequency * components.access_frequency
    )


def composite_score(
    inputs: CompositeInputs,
    weights: RankWeights | None = None,
) -> float:
    """Composite score with category-conditional recency decay."""
    return score(
        ScoreComponents(
            relevance=inputs.relevance,
            recency=recency_decay(inputs.age_days, inputs.categories),
            usefulness=inputs.usefulness,
            confidence=inputs.confidence,
            access_frequency=inputs.access_frequency,
        ),
        weights,
    )


def _require_unit_interval(name: str, value: float) -> None:
    if not math.isfinite(value) or value < 0.0 or value > 1.0:
        msg = f"{name} must be a finite value in [0, 1], got {value!r}"
        raise ValueError(msg)
