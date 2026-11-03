"""Thin pack glue: RetrievalResult + TokenBudget → PackedMemories (3.5.C.4).

Full gRPC AssembleContext orchestration (budget → retrieve → score → pack →
format via ``ContextFormatter`` / ADR-0070) remains 3.5.C.6. This module exists
so the packer has a tested call site that merges hot/cold hits, applies the
interim packer score, and packs under ``TokenBudget.usable_budget``.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import replace

from app.budget import TokenBudget
from app.conflict import collapse_conflicts
from app.packer import ContextPacker, PackedMemories, ScoredMemory
from app.retrieval import MemoryHit, RetrievalResult
from app.scoring import score_hits, score_memory_hit


def score_retrieval_hits(hits: Sequence[MemoryHit]) -> list[ScoredMemory]:
    """Dedupe, drop unresolved conflicts, then attach the interim packer score."""
    return score_hits(collapse_conflicts(_dedupe_hits(list(hits))))


def pack_retrieval(
    result: RetrievalResult,
    budget: TokenBudget,
    *,
    packer: ContextPacker,
) -> PackedMemories:
    """Dedupe hot+cold, suppress conflicts, score, and pack under usable budget.

    Preference when IDs collide: higher interim score, then lower ``rank``.
    Packs against ``budget.usable_budget`` (may be zero when the window is
    constrained). Does not format or populate gRPC metrics — that is 3.5.C.6.
    """
    scored = score_retrieval_hits(result.hot_memories + result.cold_memories)
    return packer.pack(scored, budget.usable_budget)


def _dedupe_hits(hits: list[MemoryHit]) -> list[MemoryHit]:
    """Keep one hit per memory_id — prefer higher interim score, then lower rank.

    The surviving copy keeps the **union** of the duplicates' conflict groups.
    Hot and cold read the escalation table independently, so a pending conflict
    created between the two calls can be visible to only one copy; dropping it
    would let both sides of the conflict reach the packer.
    """
    best: dict[str, MemoryHit] = {}
    groups: dict[str, set[str]] = {}
    for hit in hits:
        groups.setdefault(hit.memory_id, set()).update(hit.conflict_groups)
        existing = best.get(hit.memory_id)
        if existing is None or _prefer(hit, existing):
            best[hit.memory_id] = hit
    return [
        replace(hit, conflict_groups=tuple(sorted(groups[hit.memory_id])))
        for hit in best.values()
    ]


def _prefer(candidate: MemoryHit, incumbent: MemoryHit) -> bool:
    """Return True when ``candidate`` should replace ``incumbent`` in dedupe."""
    cand_score = score_memory_hit(candidate)
    inc_score = score_memory_hit(incumbent)
    if cand_score != inc_score:
        return cand_score > inc_score
    return candidate.rank < incumbent.rank
