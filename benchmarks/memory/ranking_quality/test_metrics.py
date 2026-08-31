"""Unit tests for ranking-quality metrics (hand-computed)."""

from __future__ import annotations

import importlib.util
import sys
import unittest
from pathlib import Path

_METRICS_PATH = Path(__file__).resolve().parent / "metrics.py"
_SPEC = importlib.util.spec_from_file_location("ranking_metrics", _METRICS_PATH)
if _SPEC is None or _SPEC.loader is None:
    raise RuntimeError("cannot load metrics")
metrics = importlib.util.module_from_spec(_SPEC)
sys.modules["ranking_metrics"] = metrics
_SPEC.loader.exec_module(metrics)


class MetricsTests(unittest.TestCase):
    def test_precision_at_5_half_hits(self) -> None:
        ranked = ["a", "b", "c", "d", "e"]
        expected = ["a", "x", "c"]
        self.assertAlmostEqual(metrics.precision_at_k(ranked, expected, 5), 2 / 5)

    def test_recall_at_10_partial(self) -> None:
        ranked = ["a", "b"]
        expected = ["a", "b", "c"]
        self.assertAlmostEqual(metrics.recall_at_k(ranked, expected, 10), 2 / 3)

    def test_mrr_first_hit_at_two(self) -> None:
        ranked = ["x", "target", "y"]
        expected = ["target"]
        self.assertAlmostEqual(metrics.mean_reciprocal_rank(ranked, expected), 0.5)

    def test_mrr_zero_when_missing(self) -> None:
        self.assertEqual(metrics.mean_reciprocal_rank(["a"], ["b"]), 0.0)

    def test_expected_order_match_perfect(self) -> None:
        ranked = ["a", "b", "c", "noise"]
        expected = ["a", "b", "c"]
        self.assertEqual(metrics.expected_order_match(ranked, expected), 1.0)

    def test_expected_order_match_detects_swapped_non_leading_keys(self) -> None:
        ranked = ["a", "c", "b", "noise", "extra"]
        expected = ["a", "b", "c"]
        self.assertEqual(metrics.expected_order_match(ranked, expected), 0.0)
        self.assertAlmostEqual(metrics.precision_at_k(ranked, expected, 5), 3 / 5)
        self.assertAlmostEqual(metrics.recall_at_k(ranked, expected, 10), 1.0)
        self.assertAlmostEqual(metrics.mean_reciprocal_rank(ranked, expected), 1.0)


if __name__ == "__main__":
    unittest.main()
