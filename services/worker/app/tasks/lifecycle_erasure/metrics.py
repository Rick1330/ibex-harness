"""Prometheus counters for the erasure consumer."""

from __future__ import annotations

from prometheus_client import Counter

ERASURE_OUTCOME = Counter(
    "ibex_worker_memory_erasure_total",
    "Memory erasure outbox rows settled, by resulting state",
    ["state"],
)
ERASURE_STORE = Counter(
    "ibex_worker_memory_erasure_store_total",
    "Per-store outcome of a memory erasure",
    ["store", "status"],
)
