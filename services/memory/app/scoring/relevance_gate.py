"""Scoring-time relevance floor (milestone 3.5.C.3 / ADR-0068).

This gate operates on the composite *relevance component* (vector cosine or the FTS
sentinel) *after* retrieval and *before* ``composite_score()``.

It is distinct from ADR-0053's retrieval-time ``min_similarity`` (default 0.70), which
filters ANN rows in pgvector before hydrate. Callers may lower ``min_similarity`` (tests,
benchmarks); the scoring-time floor remains the safety net so stale-but-frequent
low-relevance candidates never enter the weighted sum.
"""

from __future__ import annotations

import math


def passes_relevance_floor(relevance: float, floor: float) -> bool:
    """Return True when ``relevance`` is at or above the scoring-time floor.

    Boundary: ``relevance == floor`` passes (inclusive). Candidates below the floor must
    be excluded before scoring — not zeroed after a composite sum.
    """
    if not math.isfinite(relevance):
        msg = f"relevance must be finite, got {relevance!r}"
        raise ValueError(msg)
    if not math.isfinite(floor):
        msg = f"floor must be finite, got {floor!r}"
        raise ValueError(msg)
    if floor < 0.0 or floor > 1.0:
        msg = f"floor must be in [0, 1], got {floor!r}"
        raise ValueError(msg)
    return relevance >= floor
