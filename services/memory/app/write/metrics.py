"""Prometheus counters for after-commit cache/index failures."""

from __future__ import annotations

from prometheus_client import Counter

WRITE_CACHE_ERRORS = Counter(
    "ibex_memory_write_cache_errors_total",
    "After-commit cache or vector index write failures",
    ["op"],
)
