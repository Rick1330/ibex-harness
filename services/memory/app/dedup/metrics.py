"""Prometheus counters for write-path dedup outcomes (m3.C.2)."""

from __future__ import annotations

from prometheus_client import Counter

DEDUP_TOTAL = Counter(
    "ibex_memory_dedup_total",
    "Memory write dedup outcomes",
    ["result"],
)

_RESULT_EXACT = "exact_duplicate"
_RESULT_NEAR = "near_duplicate"
_RESULT_NOVEL = "novel"


def record_exact_duplicate() -> None:
    DEDUP_TOTAL.labels(result=_RESULT_EXACT).inc()


def record_near_duplicate() -> None:
    DEDUP_TOTAL.labels(result=_RESULT_NEAR).inc()


def record_novel() -> None:
    DEDUP_TOTAL.labels(result=_RESULT_NOVEL).inc()
