"""Lock RankWeights and CATEGORY_HALF_LIFE_DAYS against accidental drift (m3.D.2)."""

from __future__ import annotations

from app.scoring.composite import RankWeights
from app.scoring.half_life import CATEGORY_HALF_LIFE_DAYS


def test_rank_weights_defaults_frozen() -> None:
    weights = RankWeights()
    assert weights.relevance == 0.40
    assert weights.recency == 0.25
    assert weights.usefulness == 0.20
    assert weights.confidence == 0.10
    assert weights.frequency == 0.05


def test_category_half_life_days_frozen() -> None:
    assert CATEGORY_HALF_LIFE_DAYS == {
        "factual": 180.0,
        "procedural": 120.0,
        "preference": 45.0,
        "behavioral": 30.0,
        "episodic": 14.0,
    }
