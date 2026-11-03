"""Hand-computed tests for Cohen's kappa and its confusion matrix (ADR-0095)."""

from __future__ import annotations

import pytest

from app.eval.agreement import cohen_kappa


def _labels(*runs: tuple[str, int]) -> list[str]:
    """Build a label sequence from (label, count) runs, to keep the matrices readable."""
    return [label for label, count in runs for _ in range(count)]


class TestCohenKappa:
    def test_known_two_by_two_matrix(self) -> None:
        #         rater B
        # rater A   x    y
        #   x      20    5     (25)
        #   y      10   15     (25)
        #                  B: 30   20
        # p_o = 35/50 = 0.7 ; p_e = (25*30 + 25*20)/50^2 = 0.5 ; kappa = 0.4
        a = _labels(("x", 25), ("y", 25))
        b = _labels(("x", 20), ("y", 5), ("x", 10), ("y", 15))

        result = cohen_kappa(a, b)

        assert result.kappa == pytest.approx(0.4)
        assert result.observed_agreement == pytest.approx(0.7)
        assert result.expected_agreement == pytest.approx(0.5)
        assert result.item_count == 50
        assert result.agreed_items() == 35
        assert dict(result.confusion) == {("x", "x"): 20, ("x", "y"): 5, ("y", "x"): 10, ("y", "y"): 15}

    def test_perfect_agreement_is_one(self) -> None:
        a = _labels(("x", 10), ("y", 10))

        result = cohen_kappa(a, list(a))

        assert result.kappa == pytest.approx(1.0)
        assert result.observed_agreement == pytest.approx(1.0)

    def test_a_single_category_used_by_both_raters_is_undefined(self) -> None:
        # p_e = 1, so (p_o - p_e)/(1 - p_e) is 0/0. Reporting 1.0 would let a degenerate
        # design pass the gate.
        result = cohen_kappa(["x", "x", "x"], ["x", "x", "x"])

        assert result.kappa is None
        assert result.defined is False
        assert result.observed_agreement == pytest.approx(1.0)
        assert result.expected_agreement == pytest.approx(1.0)

    def test_prevalence_makes_high_agreement_score_near_zero(self) -> None:
        # 48 of 50 items agree (96 %) but one category dominates, so kappa is negative.
        # This is why the report carries the observed agreement beside the statistic.
        a = _labels(("x", 49), ("y", 1))
        b = _labels(("x", 48), ("y", 1), ("x", 1))

        result = cohen_kappa(a, b)

        assert result.observed_agreement == pytest.approx(0.96)
        assert result.expected_agreement == pytest.approx(0.9608)
        assert result.kappa == pytest.approx((0.96 - 0.9608) / (1 - 0.9608))
        assert result.kappa is not None
        assert result.kappa < 0.0

    def test_declared_categories_do_not_change_the_number(self) -> None:
        a = _labels(("x", 25), ("y", 25))
        b = _labels(("x", 20), ("y", 5), ("x", 10), ("y", 15))

        inferred = cohen_kappa(a, b)
        declared = cohen_kappa(a, b, categories=("x", "y", "z"))

        assert declared.kappa == pytest.approx(inferred.kappa)
        assert declared.categories == ("x", "y", "z")
        assert inferred.categories == ("x", "y")

    def test_an_unused_declared_category_still_gets_its_matrix_cells(self) -> None:
        # A report writer iterating the categories must find a cell for every pair; a
        # sparse matrix would drop "z" or raise KeyError in their renderer.
        a = _labels(("x", 2), ("y", 1))
        b = _labels(("x", 2), ("y", 1))

        result = cohen_kappa(a, b, categories=("x", "y", "z"))

        assert len(result.confusion) == 9
        assert result.confusion[("z", "z")] == 0
        assert result.confusion[("z", "x")] == 0
        assert result.confusion[("x", "z")] == 0
        assert result.confusion[("x", "x")] == 2

    def test_label_outside_the_declared_categories_is_rejected(self) -> None:
        with pytest.raises(ValueError, match="outside the declared categories"):
            cohen_kappa(["x", "y"], ["x", "z"], categories=("x", "y"))

    def test_empty_declared_categories_are_rejected(self) -> None:
        with pytest.raises(ValueError, match="at least one category"):
            cohen_kappa(["x"], ["x"], categories=())

    def test_duplicate_categories_are_rejected(self) -> None:
        with pytest.raises(ValueError, match="unique"):
            cohen_kappa(["x"], ["x"], categories=("x", "x"))

    def test_length_mismatch_is_rejected(self) -> None:
        with pytest.raises(ValueError, match="differ in length"):
            cohen_kappa(["x"], ["x", "y"])

    def test_empty_input_is_rejected(self) -> None:
        with pytest.raises(ValueError, match="at least one item"):
            cohen_kappa([], [])

    def test_symmetric_under_swapping_the_raters(self) -> None:
        a = _labels(("x", 25), ("y", 25))
        b = _labels(("x", 20), ("y", 5), ("x", 10), ("y", 15))

        assert cohen_kappa(a, b).kappa == pytest.approx(cohen_kappa(b, a).kappa)
