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
    assert len(kept) == 1
    assert kept[0]["min_similarity"] == 0.70


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
    assert gate["has_1m"] is False
    assert compute_status(gate) == "warn"


def test_status_fail_on_low_recall() -> None:
    cells = [
        {
            "corpus_size": 10_000,
            "recall_at_10": 0.5,
            "latency_ms_p95": 20.0,
            "latency_ms_p99": 22.0,
        }
    ]
    assert compute_status(compute_gate_summary(cells)) == "fail"
