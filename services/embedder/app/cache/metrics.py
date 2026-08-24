"""Prometheus counters for embedding cache hit/miss and Redis errors."""

from __future__ import annotations

from prometheus_client import Counter

CACHE_REQUESTS = Counter(
    "ibex_embedder_cache_requests_total",
    "Embedding cache lookups per text",
    ["backend", "result"],
)

CACHE_ERRORS = Counter(
    "ibex_embedder_cache_errors_total",
    "Embedding cache Redis failures (fail-open path)",
    ["op"],
)


def record_hit(backend: str) -> None:
    CACHE_REQUESTS.labels(backend=backend, result="hit").inc()


def record_miss(backend: str) -> None:
    CACHE_REQUESTS.labels(backend=backend, result="miss").inc()


def record_error(op: str) -> None:
    CACHE_ERRORS.labels(op=op).inc()
