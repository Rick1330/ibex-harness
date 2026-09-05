"""Composite scoring v2 — category-conditional recency decay + relevance gate."""

from __future__ import annotations

from app.scoring.composite import (
    CompositeInputs,
    RankWeights,
    ScoreComponents,
    composite_score,
    score,
)
from app.scoring.half_life import (
    CATEGORY_HALF_LIFE_DAYS,
    MemoryCategory,
    half_life_days,
    recency_decay,
)
from app.scoring.relevance_gate import passes_relevance_floor

__all__ = [
    "CATEGORY_HALF_LIFE_DAYS",
    "CompositeInputs",
    "MemoryCategory",
    "RankWeights",
    "ScoreComponents",
    "composite_score",
    "half_life_days",
    "passes_relevance_floor",
    "recency_decay",
    "score",
]
