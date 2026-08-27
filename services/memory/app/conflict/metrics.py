"""Prometheus metrics for temporal conflict detection (m3.C.3)."""

from __future__ import annotations

from prometheus_client import Counter

CONFLICTS_TOTAL = Counter(
    "ibex_memory_conflicts_total",
    "Memory write conflict outcomes",
    ["outcome"],
)

CONFLICT_LLM_CALLS = Counter(
    "ibex_memory_conflict_llm_calls_total",
    "LLM classifier invocations during conflict detection",
)


def record_outcome(outcome: str) -> None:
    CONFLICTS_TOTAL.labels(outcome=outcome).inc()


def record_llm_call() -> None:
    CONFLICT_LLM_CALLS.inc()
