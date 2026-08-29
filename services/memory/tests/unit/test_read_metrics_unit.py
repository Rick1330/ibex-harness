"""Unit tests for read-path Prometheus metrics."""

from __future__ import annotations

from prometheus_client import REGISTRY

from app.read.metrics import SEARCH_FALLBACK


def test_search_fallback_metric_registered() -> None:
    assert "ibex_memory_search_fallback_total" in REGISTRY._names_to_collectors
    SEARCH_FALLBACK.labels(triggered="true").inc()
