"""Interim packer scoring from MemoryHit fields (milestone 3.5.C.4 / ADR-0069).

IMPORTANT: This is **not** ``services/memory/app/scoring/composite.py``'s
``composite_score``. Memory ranks with relevance / recency / usefulness /
confidence / access frequency, but the HTTP search/hot payloads consumed by
context only expose ``similarity``, ``confidence``, and ``rank`` (no numeric
composite on the wire). Until memory returns the real composite (follow-up),
the packer optimizes this labeled interim score:

    0.85 * similarity + 0.15 * confidence

``rank`` is used only as a stable tie-break when building ``ScoredMemory`` lists
elsewhere; it is not part of the weighted sum.
"""

from __future__ import annotations

import math
from collections.abc import Sequence

from app.packer import ScoredMemory
from app.retrieval import MemoryHit

_SIMILARITY_WEIGHT = 0.85
_CONFIDENCE_WEIGHT = 0.15


def score_memory_hit(hit: MemoryHit) -> float:
    """Return the interim packer score for one hit (finite, in approximately [0, 1])."""
    _require_unit("similarity", hit.similarity)
    _require_unit("confidence", hit.confidence)
    return _SIMILARITY_WEIGHT * hit.similarity + _CONFIDENCE_WEIGHT * hit.confidence


def score_hits(hits: Sequence[MemoryHit]) -> list[ScoredMemory]:
    """Wrap each hit with its interim packer score."""
    return [ScoredMemory(hit=hit, composite_score=score_memory_hit(hit)) for hit in hits]


def _require_unit(name: str, value: object) -> None:
    number = _as_finite_float(name, value)
    if number < 0.0 or number > 1.0:
        msg = f"{name} must be in [0, 1], got {number!r}"
        raise ValueError(msg)


def _as_finite_float(name: str, value: object) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        msg = f"{name} must be a number, got {value!r}"
        raise TypeError(msg)
    number = float(value)
    if not math.isfinite(number):
        msg = f"{name} must be finite, got {number!r}"
        raise ValueError(msg)
    return number
