"""Unresolved-conflict suppression across the hot + cold merge (5.B.2 / ADR-0094).

The memory service keeps only one side of a pending contradiction inside a
single page. Context assembly merges two pages -- the hot cache and the cold
search -- and each can carry the other side of the same conflict, so the rule
runs again here on the merged list.

Winner selection uses the packer's interim score (``0.85 * similarity +
0.15 * confidence``), which is the only comparable ordering across hot and cold:
hot scores are write-time ZSET scores, cold scores are query similarity. Ties
break on ``memory_id`` so the outcome never depends on branch completion order.
"""

from __future__ import annotations

from collections.abc import Sequence

from app.retrieval import MemoryHit
from app.scoring import score_memory_hit


def collapse_conflicts(hits: Sequence[MemoryHit]) -> list[MemoryHit]:
    """Keep the highest-scoring side of every unresolved conflict.

    The rule is pairwise: a hit is dropped when it shares a pending escalation
    with a hit already kept. The survivor set therefore contains no conflicting
    pair, which is the property the packer needs -- both sides must never reach
    the formatter.
    """
    ordered = sorted(hits, key=lambda hit: (-score_memory_hit(hit), hit.memory_id))
    kept: list[MemoryHit] = []
    kept_groups: set[str] = set()
    for hit in ordered:
        if hit.conflict_groups and not kept_groups.isdisjoint(hit.conflict_groups):
            continue
        kept.append(hit)
        kept_groups.update(hit.conflict_groups)
    return kept
