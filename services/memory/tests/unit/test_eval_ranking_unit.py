"""Hand-computed tests for the ranking metrics (ADR-0095).

Every expected value here is derived from the formula in the test, not from the
implementation, so a changed definition fails rather than silently re-baselining.
"""

from __future__ import annotations

import math
from collections.abc import Sequence

import pytest

from app.eval.ranking import ndcg_at_k, rbo, top1_agreement


def _dcg(gains: Sequence[float]) -> float:
    return sum(gain / math.log2(position) for position, gain in enumerate(gains, start=2))


def _gain(level: float) -> float:
    return 2.0**level - 1.0


class TestNdcg:
    def test_ideal_order_scores_one(self) -> None:
        gains = {"a": 2.0, "b": 1.0}
        assert ndcg_at_k(["a", "b"], gains, k=2) == pytest.approx(1.0)

    def test_reversed_order_is_discounted(self) -> None:
        gains = {"a": 2.0, "b": 1.0}
        expected = _dcg([_gain(1.0), _gain(2.0)]) / _dcg([_gain(2.0), _gain(1.0)])

        assert ndcg_at_k(["b", "a"], gains, k=2) == pytest.approx(expected)
        assert expected == pytest.approx(0.7967, abs=5e-4)

    def test_unjudged_document_scores_no_gain(self) -> None:
        # "x" was never judged, so it contributes 0 and pushes "a" down one rank.
        expected = _dcg([0.0, _gain(1.0)]) / _dcg([_gain(1.0)])

        assert ndcg_at_k(["x", "a"], {"a": 1.0}, k=2) == pytest.approx(expected)
        assert expected == pytest.approx(0.6309, abs=5e-4)

    def test_graded_judgments_see_a_quality_error_that_binary_ones_cannot(self) -> None:
        # "b" is relevant and "a" is highly relevant, but the ranking puts "b" first.
        # With graded judgments that is a measurable loss; with binary judgments the
        # page is indistinguishable from the correct one, which is the whole reason the
        # gold set v2 carries grades instead of a click-like binary label.
        ranked = ["b", "a"]
        graded = ndcg_at_k(ranked, {"a": 3.0, "b": 1.0}, k=2)
        binary = ndcg_at_k(ranked, {"a": 1.0, "b": 1.0}, k=2)

        assert graded == pytest.approx(_dcg([_gain(1.0), _gain(3.0)]) / _dcg([_gain(3.0), _gain(1.0)]))
        assert 0.0 < graded < 1.0
        assert binary == pytest.approx(1.0)

    def test_truncation_ignores_documents_beyond_k(self) -> None:
        gains = {"a": 1.0, "b": 3.0}

        # k=1 sees only "a"; the much better "b" at rank 2 cannot rescue the score.
        assert ndcg_at_k(["a", "b"], gains, k=1) == pytest.approx(1.0 / _gain(3.0))

    def test_k_larger_than_the_ranking(self) -> None:
        expected = _dcg([_gain(2.0)]) / _dcg([_gain(3.0), _gain(2.0)])

        assert ndcg_at_k(["a"], {"a": 2.0, "b": 3.0}, k=10) == pytest.approx(expected)

    def test_no_judgments_is_zero_not_one(self) -> None:
        assert ndcg_at_k(["a", "b"], {}, k=5) == 0.0

    def test_all_zero_gains_is_zero(self) -> None:
        assert ndcg_at_k(["a"], {"a": 0.0}, k=5) == 0.0

    def test_empty_ranking_is_zero(self) -> None:
        assert ndcg_at_k([], {"a": 1.0}, k=5) == 0.0

    def test_grade_zero_documents_do_not_inflate_the_ideal(self) -> None:
        # Only the judged-positive document can be found; finding it is a perfect score.
        gains = {"a": 1.0, "z": 0.0}

        assert ndcg_at_k(["a"], gains, k=2) == pytest.approx(1.0)

    def test_a_repeated_id_is_rejected_rather_than_scoring_perfect(self) -> None:
        # Crediting one judgment twice pushes actual above ideal, and the clamp would
        # turn that into a tidy 1.0 — the worst possible direction for a quality metric.
        with pytest.raises(ValueError, match="duplicate"):
            ndcg_at_k(["a", "a"], {"a": 3.0}, k=2)

    def test_negative_gain_is_rejected(self) -> None:
        with pytest.raises(ValueError, match="non-negative"):
            ndcg_at_k(["a"], {"a": -1.0}, k=1)

    def test_non_finite_gain_is_rejected(self) -> None:
        with pytest.raises(ValueError, match="finite"):
            ndcg_at_k(["a"], {"a": math.inf}, k=1)

    @pytest.mark.parametrize("k", [0, -1])
    def test_k_below_one_is_rejected(self, k: int) -> None:
        with pytest.raises(ValueError, match="k must be"):
            ndcg_at_k(["a"], {"a": 1.0}, k=k)

    def test_boolean_k_is_rejected(self) -> None:
        # ``True`` is an int in Python; accepting it would silently mean k=1.
        with pytest.raises(TypeError, match="k must be an integer"):
            ndcg_at_k(["a"], {"a": 1.0}, k=True)


class TestRbo:
    def test_identical_rankings_score_one(self) -> None:
        ranking = ["a", "b", "c", "d", "e"]

        assert rbo(ranking, ranking) == pytest.approx(1.0)

    def test_disjoint_rankings_score_zero(self) -> None:
        assert rbo(["a", "b", "c"], ["x", "y", "z"]) == 0.0

    def test_reversed_page_keeps_the_conjoint_tail(self) -> None:
        # Prefix agreements for a fully reversed five-item page:
        #   A_1 = 0, A_2 = 0, A_3 = 1/3 ("c"), A_4 = 3/4 ("b", "c", "d"), A_5 = 1
        # sum_{d=1..5} 0.1 * 0.9**(d-1) * A_d = 0.027 + 0.054675 + 0.06561 = 0.147285
        # tail 0.9**5 * A_5                                       = 0.59049
        expected = 0.1 * 0.9**2 * (1 / 3) + 0.1 * 0.9**3 * (3 / 4) + 0.1 * 0.9**4 + 0.9**5

        assert rbo(["a", "b", "c", "d", "e"], ["e", "d", "c", "b", "a"]) == pytest.approx(expected)
        assert expected == pytest.approx(0.737775)

    def test_swapping_the_top_two_costs_the_top_weight(self) -> None:
        # A_1 = 0, A_2 = 1, A_3 = 1  ->  0.1*0 + 0.09*1 + 0.081*1 = 0.171, tail 0.729.
        expected = 0.09 + 0.081 + 0.9**3

        assert rbo(["a", "b", "c"], ["b", "a", "c"]) == pytest.approx(expected)
        assert expected == pytest.approx(0.9)

    def test_a_lower_persistence_weights_the_top_more(self) -> None:
        a, b = ["a", "b", "c"], ["b", "a", "c"]

        # p=0.5: 0.5*0 + 0.25*1 + 0.125*1 = 0.375, tail 0.125.
        assert rbo(a, b, p=0.5) == pytest.approx(0.5)
        assert rbo(a, b, p=0.9) == pytest.approx(0.9)

    def test_symmetric(self) -> None:
        a = ["x", "y", "z", "w"]
        b = ["y", "x", "w", "z"]

        assert rbo(a, b) == pytest.approx(rbo(b, a))

    def test_honours_a_shorter_depth(self) -> None:
        a = ["a", "b", "c", "d"]
        b = ["a", "b", "x", "y"]

        # Cutting at k=2 hides the disagreement below the second rank.
        assert rbo(a, b, k=2) == pytest.approx(1.0)
        assert rbo(a, b, k=4) < 1.0

    def test_partial_overlap_is_between_zero_and_one(self) -> None:
        value = rbo(["a", "b", "c", "d"], ["a", "c", "b", "z"])

        assert 0.0 < value < 1.0

    def test_empty_rankings_agree(self) -> None:
        assert rbo([], []) == 1.0

    def test_one_empty_ranking_disagrees(self) -> None:
        assert rbo(["a"], []) == 0.0

    def test_duplicate_ids_are_rejected(self) -> None:
        with pytest.raises(ValueError, match="duplicate"):
            rbo(["a", "a"], ["a", "b"])

    @pytest.mark.parametrize("p", [0.0, 1.0, -0.5, 2.0])
    def test_invalid_persistence_is_rejected(self, p: float) -> None:
        with pytest.raises(ValueError, match="persistence"):
            rbo(["a"], ["a"], p=p)

    def test_depth_beyond_the_shorter_ranking_is_rejected(self) -> None:
        with pytest.raises(ValueError, match="exceeds the shorter ranking"):
            rbo(["a", "b"], ["a", "b", "c"], k=3)

    @pytest.mark.parametrize(("page_a", "page_b"), [([], []), ([], ["a"]), (["a"], [])])
    def test_an_invalid_depth_is_rejected_even_when_a_page_is_empty(
        self, page_a: list[str], page_b: list[str]
    ) -> None:
        # Otherwise k=0 is legal exactly where nothing was retrieved and illegal elsewhere,
        # which is the failure mode that only shows up in production traffic.
        with pytest.raises(ValueError, match="k must be"):
            rbo(page_a, page_b, k=0)


class TestTop1Agreement:
    def test_same_top_hit(self) -> None:
        assert top1_agreement(["a", "b"], ["a", "c"]) == 1.0

    def test_different_top_hit(self) -> None:
        assert top1_agreement(["a", "b"], ["b", "a"]) == 0.0

    def test_empty_ranking(self) -> None:
        assert top1_agreement([], ["a"]) == 0.0
