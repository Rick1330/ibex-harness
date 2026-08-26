"""Unit tests for published HNSW cell filtering and gate summary."""

from __future__ import annotations

import sys
from pathlib import Path

_BENCH = Path(__file__).resolve().parents[1] / "memory"
sys.path.insert(0, str(_BENCH))

from build_published_data import (  # noqa: E402
    compute_gate_summary,
    compute_status,
    filter_published_results,
)


def _expect(condition: bool, message: str) -> None:
    """Fail tests without `assert` (Codacy flags assert under -O)."""
    if not condition:
        raise AssertionError(message)


def test_filter_keeps_production_cells_only() -> None:
    results = [
        {
            "corpus_size": 10_000,
            "recall_at_10": 1.0,
            "latency_ms_p95": 20.0,
            "latency_ms_p99": 22.0,
            "ef_search": 40,
            "min_similarity": 0.0,
            "iterative_scan": "off",
            "index_build_mode": "bulk",
        },
        {
            "corpus_size": 10_000,
            "recall_at_10": 1.0,
            "latency_ms_p95": 20.0,
            "latency_ms_p99": 22.0,
            "ef_search": 40,
            "min_similarity": 0.70,
            "iterative_scan": "off",
            "index_build_mode": "bulk",
        },
    ]
    kept = filter_published_results(results)
    _expect(len(kept) == 1, "expected one production cell")
    _expect(kept[0]["min_similarity"] == 0.70, "expected min_similarity 0.70")


def test_status_warn_without_1m() -> None:
    cells = [
        {
            "corpus_size": 10_000,
            "recall_at_10": 1.0,
            "latency_ms_p95": 20.0,
            "latency_ms_p99": 22.0,
        }
    ]
    gate = compute_gate_summary(cells)
    _expect(gate["has_1m"] is False, "expected has_1m false")
    _expect(compute_status(gate) == "warn", "expected warn without 1M")


def test_status_fail_on_low_recall() -> None:
    cells = [
        {
            "corpus_size": 10_000,
            "recall_at_10": 0.5,
            "latency_ms_p95": 20.0,
            "latency_ms_p99": 22.0,
        }
    ]
    _expect(compute_status(compute_gate_summary(cells)) == "fail", "expected fail")
