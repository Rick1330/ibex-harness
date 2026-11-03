"""Prometheus metrics for memory read/search path (milestone 3.D.1)."""

from __future__ import annotations

from prometheus_client import Counter, Histogram

SEARCH_FALLBACK = Counter(
    "ibex_memory_search_fallback_total",
    "Full-text search fallback invocations on find_similar",
    ["triggered"],
)

SEARCH_HYBRID = Counter(
    "ibex_memory_search_hybrid_total",
    "Hybrid retrieval invocations on find_similar, by channel that returned hits",
    ["vector", "full_text"],
)

RERANK = Counter(
    "ibex_memory_rerank_total",
    "Cross-encoder rerank outcomes on find_similar",
    ["result"],
)

RERANK_LATENCY = Histogram(
    "ibex_memory_rerank_seconds",
    "Cross-encoder rerank latency on find_similar",
    buckets=(0.025, 0.05, 0.1, 0.15, 0.25, 0.5, 1.0),
)

HOT_CACHE_READ = Counter(
    "ibex_memory_hot_cache_read_total",
    "Hot cache read invocations via get_hot_memories",
    ["result"],
)

PII_RECONFIRM = Counter(
    "ibex_memory_read_pii_reconfirm_total",
    "Tier-1 structured PII read-path re-check on hydrated results",
    ["result"],
)
