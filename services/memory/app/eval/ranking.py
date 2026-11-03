"""Ranking metrics for graded relevance and rank-shift comparison.

Two different questions get two different measures:

* **How good is one ordering?** ``ndcg_at_k`` — graded relevance, position-discounted, and
  comparable across queries because the ideal ordering normalises it to ``[0, 1]``.
  Set-overlap metrics (precision/recall/MRR) treat "highly relevant at rank 3" and "barely
  relevant at rank 3" as identical, which is exactly the distinction a cross-encoder is
  supposed to improve.
* **How far did the ordering move?** ``rbo`` — rank-biased overlap (Webber, Moffat & Zobel,
  TOIS 2010). It is top-weighted, tolerates a page whose tail differs, and needs no shared
  judged set, so it can compare a live ranking against a candidate one on traffic nobody
  labelled.

Both are pure functions over sequences of document ids; neither knows anything about tenants,
HTTP, or the database.
"""

from __future__ import annotations

import math
from collections.abc import Mapping, Sequence

# Gain for a judged relevance level. Exponential gain is the standard choice because it
# keeps the difference between "relevant" and "highly relevant" visible after discounting;
# linear gain compresses it and makes a graded set behave like a binary one.
_GAIN_BASE = 2.0


def ndcg_at_k(ranked: Sequence[str], gains: Mapping[str, float], k: int) -> float:
    """Normalised discounted cumulative gain at ``k`` with graded relevance.

    ``gains`` holds the judged relevance of each document, normally ``0..3``. A document
    that is absent from the map was never judged and scores ``0`` — the pooled-judgment
    convention: an unjudged document is not evidence of relevance, and pretending otherwise
    rewards retrievers for returning documents nobody assessed.

    Returns ``0.0`` when there is no achievable gain at all (empty rankings, no judged
    documents, or every judgment ``0``), because a perfect score must mean "found everything
    worth finding", not "the query had nothing to find".

    The ranking must be duplicate-free: a repeated id would credit one judgment twice and
    inflate the score, so it is treated as a construction bug rather than silently deduped.
    """
    _require_depth(k, "k")
    _require_unique(ranked, "ranked")
    if not ranked or not gains:
        return 0.0
    ideal = _ideal_dcg(gains, k)
    if ideal <= 0.0:
        return 0.0
    actual = _dcg([_gain_of(ranked, gains, index) for index in range(min(k, len(ranked)))])
    # Floating-point error can push a perfect ordering a hair above 1.0.
    return min(1.0, actual / ideal)


def rbo(
    ranking_a: Sequence[str],
    ranking_b: Sequence[str],
    *,
    p: float = 0.9,
    k: int | None = None,
) -> float:
    """Rank-biased overlap with a tail extrapolation, in ``[0, 1]``.

    ``p`` is the persistence: the weight of the agreement at depth ``d`` decays as
    ``p**(d-1)``. At ``p = 0.5`` only the first few positions matter; at ``p = 0.9`` the
    whole page does. The default of ``0.9`` keeps a ten-item page relevant while still
    letting the top three dominate.

    **The tail term is not optional here.** The plain truncated sum tops out at
    ``1 - p**k`` (about ``0.65`` for a ten-item page at ``p = 0.9``), so two *identical*
    rankings would score ``0.65`` and every divergence report would carry a large constant
    offset. Adding ``p**k * A_k`` — the standard extrapolation, "assume the agreement seen
    at depth ``k`` continues" — makes identical rankings score exactly ``1.0`` and disjoint
    rankings ``0.0``, which is what a divergence number has to mean.

    ``k`` defaults to the shorter ranking and must not exceed it: overlap past the shorter
    page is not defined, so a larger ``k`` is a caller error rather than a silent clamp.
    Rankings must be duplicate-free. Empty pages are normal read-path outcomes: two empty
    pages agree (``1.0``), and one empty page disagrees (``0.0``).
    """
    _require_persistence(p)
    _require_unique(ranking_a, "ranking_a")
    _require_unique(ranking_b, "ranking_b")
    if k is not None:
        _require_depth(k, "k")
    if not ranking_a and not ranking_b:
        return 1.0
    if not ranking_a or not ranking_b:
        return 0.0
    shortest = min(len(ranking_a), len(ranking_b))
    depth = shortest if k is None else k
    if depth > shortest:
        msg = f"k={depth} exceeds the shorter ranking ({shortest})"
        raise ValueError(msg)
    return _prefix_weighted_agreement(ranking_a, ranking_b, depth, p)


def top1_agreement(ranking_a: Sequence[str], ranking_b: Sequence[str]) -> float:
    """``1.0`` when both rankings put the same document first, else ``0.0``.

    Reported beside RBO because it answers a different question: a page can keep its
    quality and still change the top hit, and that is the change users notice.
    """
    if not ranking_a or not ranking_b:
        return 0.0
    return 1.0 if ranking_a[0] == ranking_b[0] else 0.0


def _prefix_weighted_agreement(
    ranking_a: Sequence[str],
    ranking_b: Sequence[str],
    depth: int,
    p: float,
) -> float:
    """``Σ (1-p)·p^(d-1)·A_d`` up to ``depth``, plus the ``p^depth·A_depth`` tail."""
    seen_a: set[str] = set()
    seen_b: set[str] = set()
    weighted = 0.0
    agreement = 0.0
    for index in range(depth):
        seen_a.add(ranking_a[index])
        seen_b.add(ranking_b[index])
        agreement = len(seen_a & seen_b) / (index + 1)
        weighted += (1.0 - p) * (p**index) * agreement
    return min(1.0, max(0.0, weighted + (p**depth) * agreement))


def _gain_of(ranked: Sequence[str], gains: Mapping[str, float], index: int) -> float:
    return _gain_value(gains.get(ranked[index], 0.0))


def _gain_value(raw: float) -> float:
    value = float(raw)
    if not math.isfinite(value) or value < 0.0:
        msg = f"relevance gain must be a finite non-negative number, got {raw!r}"
        raise ValueError(msg)
    return _GAIN_BASE**value - 1.0


def _dcg(gains: Sequence[float]) -> float:
    return sum(gain / math.log2(position + 1) for position, gain in enumerate(gains, start=1))


def _ideal_dcg(gains: Mapping[str, float], k: int) -> float:
    ordered = sorted((_gain_value(value) for value in gains.values()), reverse=True)[:k]
    # Zeros sort last, so dropping them cannot move a positive gain to another rank.
    return _dcg([gain for gain in ordered if gain > 0.0])


def _require_depth(k: int, name: str) -> None:
    _require_integer(k, name)
    if k >= 1:
        return
    msg = f"{name} must be an integer >= 1, got {k!r}"
    raise ValueError(msg)


def _require_integer(value: object, name: str) -> None:
    """Wrong type is a ``TypeError``; a wrong value stays a ``ValueError``."""
    if isinstance(value, bool) or not isinstance(value, int):
        msg = f"{name} must be an integer, got {value!r}"
        raise TypeError(msg)


def _require_persistence(p: float) -> None:
    if not 0.0 < p < 1.0:
        msg = f"persistence p must be between 0 and 1 (exclusive), got {p!r}"
        raise ValueError(msg)


def _require_unique(ranking: Sequence[str], name: str) -> None:
    if len(set(ranking)) != len(ranking):
        msg = f"{name} contains duplicate ids"
        raise ValueError(msg)
