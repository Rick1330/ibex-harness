"""Unit tests for extraction eval scoring (no LLM)."""

from __future__ import annotations

import unittest

from match import content_similarity
from metrics import (
    CATEGORIES,
    _normalize_temporal,
    _temporal_fields_match,
    aggregate_scores,
    match_memories,
    normalize_content,
    score_turn,
)


def _mem(content: str, *labels: str, valid_until: str | None = None) -> dict:
    return {
        "content": content,
        "categories": [{"label": lab, "confidence": 0.9} for lab in labels],
        "confidence": 0.9,
        "valid_from": None,
        "valid_until": valid_until,
    }


class MetricsTests(unittest.TestCase):
    def test_normalize_content_collapses_whitespace(self) -> None:
        self.assertEqual(normalize_content("  Hello   WORLD \n"), "hello world")

    def test_exact_match_perfect_scores(self) -> None:
        expected = [_mem("User prefers dark mode in the IDE", "preference")]
        predicted = [_mem("User prefers dark mode in the IDE", "preference")]
        turn = score_turn(predicted, expected, temporal_kinds=["indefinite"])
        metrics = aggregate_scores([turn])
        self.assertEqual(metrics["precision_preference"], 1.0)
        self.assertEqual(metrics["recall_preference"], 1.0)
        self.assertEqual(metrics["category_assignment_accuracy"], 1.0)
        self.assertEqual(metrics["temporal_field_accuracy"], 1.0)

    def test_over_label_penalizes_category_assignment(self) -> None:
        expected = [_mem("User prefers dark mode in the IDE", "preference")]
        predicted = [
            _mem("User prefers dark mode in the IDE", "preference", "behavioral")
        ]
        turn = score_turn(predicted, expected, temporal_kinds=["indefinite"])
        metrics = aggregate_scores([turn])
        self.assertEqual(metrics["category_assignment_accuracy"], 0.0)
        self.assertEqual(metrics["precision_preference"], 1.0)
        self.assertEqual(metrics["precision_behavioral"], 0.0)

    def test_under_label_penalizes_category_assignment(self) -> None:
        expected = [
            _mem("User prefers dark mode and uses vim daily", "preference", "behavioral")
        ]
        predicted = [_mem("User prefers dark mode and uses vim daily", "preference")]
        turn = score_turn(predicted, expected, temporal_kinds=["indefinite"])
        metrics = aggregate_scores([turn])
        self.assertEqual(metrics["category_assignment_accuracy"], 0.0)
        self.assertEqual(metrics["recall_behavioral"], 0.0)

    def test_unmatched_predicted_is_false_positive(self) -> None:
        expected = [_mem("Company HQ is in Austin Texas USA", "factual")]
        predicted = [
            _mem("Company HQ is in Austin Texas USA", "factual"),
            _mem("Hallucinated favorite color is purple now", "preference"),
        ]
        turn = score_turn(predicted, expected, temporal_kinds=["indefinite"])
        metrics = aggregate_scores([turn])
        self.assertEqual(metrics["precision_preference"], 0.0)
        self.assertEqual(metrics["recall_factual"], 1.0)
        self.assertEqual(metrics["category_assignment_accuracy"], 0.5)

    def test_unmatched_expected_is_false_negative(self) -> None:
        expected = [
            _mem("Company HQ is in Austin Texas USA", "factual"),
            _mem("User prefers dark mode in the IDE", "preference"),
        ]
        predicted = [_mem("Company HQ is in Austin Texas USA", "factual")]
        turn = score_turn(predicted, expected, temporal_kinds=["indefinite", "indefinite"])
        metrics = aggregate_scores([turn])
        self.assertEqual(metrics["recall_preference"], 0.0)
        self.assertEqual(metrics["precision_factual"], 1.0)

    def test_temporal_supersession_requires_valid_until(self) -> None:
        expected = [
            _mem(
                "User works at Acme Corp as an engineer",
                "factual",
                valid_until="2026-06-01T00:00:00Z",
            )
        ]
        predicted = [_mem("User works at Acme Corp as an engineer", "factual")]
        bad = score_turn(predicted, expected, temporal_kinds=["supersession"])
        self.assertEqual(aggregate_scores([bad])["temporal_field_accuracy"], 0.0)

        good_pred = [
            _mem(
                "User works at Acme Corp as an engineer",
                "factual",
                valid_until="2026-06-01T00:00:00Z",
            )
        ]
        good = score_turn(good_pred, expected, temporal_kinds=["supersession"])
        self.assertEqual(aggregate_scores([good])["temporal_field_accuracy"], 1.0)

    def test_temporal_indefinite_requires_null_valid_until(self) -> None:
        expected = [_mem("Python is the primary language here", "factual")]
        predicted = [
            _mem(
                "Python is the primary language here",
                "factual",
                valid_until="2026-12-01T00:00:00Z",
            )
        ]
        turn = score_turn(predicted, expected, temporal_kinds=["indefinite"])
        self.assertEqual(aggregate_scores([turn])["temporal_field_accuracy"], 0.0)

    def test_temporal_unmatched_expected_gets_no_credit(self) -> None:
        expected = [_mem("User prefers dark mode in the IDE", "preference")]
        turn = score_turn([], expected, temporal_kinds=["indefinite"])
        self.assertEqual(aggregate_scores([turn])["temporal_field_accuracy"], 0.0)

    def test_temporal_wrong_valid_from_fails(self) -> None:
        expected = [
            {
                "content": "Company HQ is in Austin Texas USA",
                "categories": [{"label": "factual", "confidence": 0.9}],
                "confidence": 0.9,
                "valid_from": "2026-01-01T00:00:00Z",
                "valid_until": None,
            }
        ]
        predicted = [
            {
                "content": "Company HQ is in Austin Texas USA",
                "categories": [{"label": "factual", "confidence": 0.9}],
                "confidence": 0.9,
                "valid_from": "2025-01-01T00:00:00Z",
                "valid_until": None,
            }
        ]
        turn = score_turn(predicted, expected, temporal_kinds=["indefinite"])
        self.assertEqual(aggregate_scores([turn])["temporal_field_accuracy"], 0.0)

    def test_score_turn_rejects_mismatched_temporal_kinds(self) -> None:
        predicted = [_mem("User prefers dark mode in the IDE", "preference")]
        expected = [
            _mem("User prefers dark mode in the IDE", "preference"),
            _mem("Company HQ is in Austin Texas USA", "factual"),
        ]
        with self.assertRaisesRegex(ValueError, "temporal_kinds"):
            score_turn(predicted, expected, temporal_kinds=["indefinite"])

    def test_per_category_metrics_not_hidden_by_macro(self) -> None:
        turns = [
            score_turn(
                [_mem("HQ is in Austin Texas United States", "factual")],
                [_mem("HQ is in Austin Texas United States", "factual")],
                temporal_kinds=["indefinite"],
            ),
            score_turn(
                [],
                [_mem("User prefers dark mode in the IDE", "preference")],
                temporal_kinds=["indefinite"],
            ),
        ]
        metrics = aggregate_scores(turns)
        self.assertEqual(metrics["recall_factual"], 1.0)
        self.assertEqual(metrics["recall_preference"], 0.0)
        self.assertLess(metrics["recall_macro"], 1.0)

    def test_match_memories_greedy_one_to_one(self) -> None:
        predicted = [
            _mem("User prefers dark mode in the IDE", "preference"),
            _mem("Deploy uses canary then full rollout", "procedural"),
        ]
        expected = [
            _mem("User prefers dark mode in the IDE", "preference"),
            _mem("Deploy uses canary then full rollout", "procedural"),
        ]
        pairs = match_memories(predicted, expected)
        matched = {(p, e) for p, e in pairs if p is not None and e is not None}
        self.assertEqual(matched, {(0, 0), (1, 1)})

    def test_all_categories_present_in_aggregate_keys(self) -> None:
        metrics = aggregate_scores([])
        for cat in CATEGORIES:
            self.assertIn(f"precision_{cat}", metrics)
            self.assertIn(f"recall_{cat}", metrics)

    def test_content_similarity_edges_and_substring(self) -> None:
        self.assertEqual(content_similarity("", "x"), 0.0)
        self.assertEqual(
            content_similarity("user prefers dark mode", "user prefers dark"), 0.85
        )
        predicted = [
            _mem("User prefers dark mode in the IDE", "preference"),
            _mem("User prefers dark mode in the IDE tonight", "preference"),
        ]
        expected = [_mem("User prefers dark mode in the IDE", "preference")]
        pairs = match_memories(predicted, expected)
        matched = [(p, e) for p, e in pairs if p is not None and e is not None]
        self.assertEqual(len(matched), 1)

    def test_temporal_normalize_z_vs_offset_equivalent(self) -> None:
        self.assertIsNone(_normalize_temporal(None))
        self.assertIsNone(_normalize_temporal(""))
        self.assertEqual(_normalize_temporal(12), 12)
        self.assertEqual(_normalize_temporal("not-a-date"), "not-a-date")
        self.assertEqual(
            _normalize_temporal("2026-01-01T00:00:00Z"),
            _normalize_temporal("2026-01-01T00:00:00+00:00"),
        )
        self.assertTrue(
            _temporal_fields_match(
                {"valid_from": "2026-01-01T00:00:00Z", "valid_until": None},
                {"valid_from": "2026-01-01T00:00:00+00:00", "valid_until": None},
            )
        )

    def test_empty_both_sides_assignment_is_perfect(self) -> None:
        turn = score_turn([], [], temporal_kinds=[])
        self.assertEqual(aggregate_scores([turn])["category_assignment_accuracy"], 1.0)


if __name__ == "__main__":
    unittest.main()
