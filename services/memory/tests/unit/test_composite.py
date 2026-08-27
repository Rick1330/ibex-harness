from __future__ import annotations

import math

import pytest

from app.scoring.composite import (
    CompositeInputs,
    RankWeights,
    ScoreComponents,
    composite_score,
    score,
)


def test_score_default_weights_sum() -> None:
    assert score(
        ScoreComponents(
            relevance=1.0,
            recency=1.0,
            usefulness=1.0,
            confidence=1.0,
            access_frequency=1.0,
        )
    ) == pytest.approx(1.0)


def test_score_rejects_bad_weights() -> None:
    components = ScoreComponents(
        relevance=1.0,
        recency=0.0,
        usefulness=0.0,
        confidence=0.0,
        access_frequency=0.0,
    )
    weights = RankWeights(
        relevance=0.5, recency=0.5, usefulness=0.5, confidence=0, frequency=0
    )
    with pytest.raises(ValueError, match="sum to 1.0"):
        score(components, weights)


@pytest.mark.parametrize(
    ("components", "match"),
    [
        (
            ScoreComponents(
                relevance=1.5,
                recency=0.0,
                usefulness=0.0,
                confidence=0.0,
                access_frequency=0.0,
            ),
            "relevance must be a finite value",
        ),
        (
            ScoreComponents(
                relevance=0.5,
                recency=math.nan,
                usefulness=0.0,
                confidence=0.0,
                access_frequency=0.0,
            ),
            "recency must be a finite value",
        ),
    ],
)
def test_score_rejects_invalid_components(
    components: ScoreComponents, match: str
) -> None:
    with pytest.raises(ValueError, match=match):
        score(components)


def test_rank_weights_reject_negative() -> None:
    weights = RankWeights(
        relevance=-0.1,
        recency=0.4,
        usefulness=0.3,
        confidence=0.2,
        frequency=0.2,
    )
    with pytest.raises(ValueError, match="relevance must be a finite value"):
        weights.validate()


@pytest.mark.parametrize(
    ("categories", "match"),
    [
        ("factual", "sequence of strings"),
        ([123], r"categories\[0\] must be a str"),
    ],
)
def test_composite_rejects_invalid_categories(categories: object, match: str) -> None:
    inputs = CompositeInputs(
        relevance=0.9,
        age_days=1.0,
        categories=categories,  # type: ignore[arg-type]
        usefulness=0.5,
        confidence=0.8,
        access_frequency=0.1,
    )
    with pytest.raises(TypeError, match=match):
        composite_score(inputs)


def test_old_factual_outranks_fresh_episodic_at_equal_relevance() -> None:
    """Bugfix: with a global 14d half-life, a ~90d factual decays near-zero and loses
    to a 14d episodic. Category-conditional half-lives keep the factual competitive.
    """
    equal = {
        "relevance": 0.90,
        "usefulness": 0.50,
        "confidence": 0.80,
        "access_frequency": 0.10,
    }
    old_factual = composite_score(
        CompositeInputs(age_days=90.0, categories=["factual"], **equal)
    )
    fresh_episodic = composite_score(
        CompositeInputs(age_days=14.0, categories=["episodic"], **equal)
    )
    assert old_factual > fresh_episodic


def test_composite_uses_shortest_half_life_for_multi_label() -> None:
    equal = {
        "relevance": 0.80,
        "usefulness": 0.50,
        "confidence": 0.80,
        "access_frequency": 0.0,
    }
    factual_only = composite_score(
        CompositeInputs(age_days=60.0, categories=["factual"], **equal)
    )
    factual_and_episodic = composite_score(
        CompositeInputs(age_days=60.0, categories=["factual", "episodic"], **equal)
    )
    assert factual_and_episodic < factual_only
