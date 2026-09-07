"""Unit tests for Laplace usefulness scoring (3.5.E.3)."""

from __future__ import annotations

import pytest

from app.feedback.score import laplace_usefulness


@pytest.mark.parametrize(
    ("positive", "negative", "expected"),
    [
        (0, 0, 0.50),
        (1, 0, 0.67),
        (3, 0, 0.80),
        (0, 1, 0.33),
        (1, 1, 0.50),
        (9, 0, 0.91),
        (0, 9, 0.09),
    ],
)
def test_laplace_usefulness_known_points(
    positive: int, negative: int, expected: float
) -> None:
    assert laplace_usefulness(positive, negative) == pytest.approx(expected)


def test_laplace_rejects_negative_counts() -> None:
    with pytest.raises(ValueError, match="non-negative"):
        laplace_usefulness(-1, 0)
    with pytest.raises(ValueError, match="non-negative"):
        laplace_usefulness(0, -1)


def test_laplace_quantizes_to_two_decimals() -> None:
    # (2+1)/(2+1+2) = 0.6 exactly
    assert laplace_usefulness(2, 1) == 0.60


def test_laplace_clamp_bounds() -> None:
    assert 0.0 <= laplace_usefulness(10_000, 0) <= 1.0
    assert 0.0 <= laplace_usefulness(0, 10_000) <= 1.0
