"""Prometheus metrics for memory read/search path (milestone 3.D.1)."""

from __future__ import annotations

from prometheus_client import Counter

SEARCH_FALLBACK = Counter(
    "ibex_memory_search_fallback_total",
    "Full-text search fallback invocations on find_similar",
    ["triggered"],
)

HOT_CACHE_READ = Counter(
    "ibex_memory_hot_cache_read_total",
    "Hot cache read invocations via get_hot_memories",
    ["result"],
)
