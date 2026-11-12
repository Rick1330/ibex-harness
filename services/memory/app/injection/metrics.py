"""Prometheus counter for write-path quarantines (W10.4).

`engineering/MONITORING.md` §7.3 documents ``ibex_memory_quarantined_total``
with ``reason`` in ``pii|injection_risk``. This module is the single
declaration site for that counter: prometheus_client raises on a duplicate
name, so any other quarantine path (the PII stage) must call
:func:`record_quarantine` here instead of declaring its own.
"""

from __future__ import annotations

from prometheus_client import Counter

#: Label value for the prompt-injection heuristic (documented in MONITORING.md).
REASON_INJECTION = "injection_risk"

QUARANTINED_TOTAL = Counter(
    "ibex_memory_quarantined_total",
    "Memories quarantined on write, by reason",
    ["reason"],
)


def record_quarantine(reason: str) -> None:
    """Count one quarantined write. ``reason`` stays a small closed vocabulary."""
    QUARANTINED_TOTAL.labels(reason=reason).inc()
