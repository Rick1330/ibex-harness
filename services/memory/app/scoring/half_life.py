"""Category half-life table and exponential recency decay."""

from __future__ import annotations

import math
from collections.abc import Sequence
from typing import Final, Literal

MemoryCategory = Literal[
    "factual",
    "preference",
    "behavioral",
    "episodic",
    "procedural",
]

CATEGORY_HALF_LIFE_DAYS: Final[dict[str, float]] = {
    "factual": 180.0,
    "procedural": 120.0,
    "preference": 45.0,
    "behavioral": 30.0,
    "episodic": 14.0,
}

_DEFAULT_HALF_LIFE_DAYS: Final[float] = 14.0
_LN2: Final[float] = math.log(2.0)


def half_life_days(categories: Sequence[str]) -> float:
    """Return the half-life for scoring.

    Multi-label memories use the **shortest** half-life (conservative decay).
    Unknown labels fall back to the episodic default (14 days).
    """
    if not categories:
        return _DEFAULT_HALF_LIFE_DAYS
    return min(
        CATEGORY_HALF_LIFE_DAYS.get(category, _DEFAULT_HALF_LIFE_DAYS)
        for category in categories
    )


def recency_decay(age_days: float, categories: Sequence[str]) -> float:
    """Exponential decay in [0, 1] using category-conditional half-life."""
    if age_days < 0:
        msg = "age_days must be non-negative"
        raise ValueError(msg)
    hl = half_life_days(categories)
    if hl <= 0:
        msg = "half_life must be positive"
        raise ValueError(msg)
    return math.exp(-_LN2 * age_days / hl)
