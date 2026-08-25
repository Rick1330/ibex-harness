from __future__ import annotations

import math

import pytest

from app.scoring.half_life import (
    CATEGORY_HALF_LIFE_DAYS,
    half_life_days,
    recency_decay,
)


def test_half_life_table_matches_documented_defaults() -> None:
    assert CATEGORY_HALF_LIFE_DAYS == {
        "factual": 180.0,
        "procedural": 120.0,
        "preference": 45.0,
        "behavioral": 30.0,
        "episodic": 14.0,
    }


def test_half_life_empty_categories_uses_episodic_default() -> None:
    assert half_life_days([]) == 14.0


def test_half_life_multi_label_uses_shortest() -> None:
    assert half_life_days(["factual", "episodic"]) == 14.0
    assert half_life_days(["procedural", "preference"]) == 45.0


def test_recency_decay_at_half_life_is_half() -> None:
    value = recency_decay(180.0, ["factual"])
    assert value == pytest.approx(0.5, rel=1e-6)


def test_recency_decay_zero_age_is_one() -> None:
    assert recency_decay(0.0, ["episodic"]) == pytest.approx(1.0)


def test_recency_decay_rejects_negative_age() -> None:
    with pytest.raises(ValueError, match="non-negative"):
        recency_decay(-1.0, ["factual"])


def test_unknown_category_falls_back_to_14() -> None:
    assert half_life_days(["unknown"]) == 14.0
    expected = math.exp(-math.log(2.0) * 14.0 / 14.0)
    assert recency_decay(14.0, ["unknown"]) == pytest.approx(expected)
