"""Thin pack glue: RetrievalResult + TokenBudget → PackedMemories (3.5.C.4).

Full gRPC AssembleContext orchestration remains 3.5.C.6. This module exists so
the packer has a tested call site that merges hot/cold hits, applies the interim
packer score, and packs under ``TokenBudget.usable_budget``.
"""

from __future__ import annotations

from app.budget import TokenBudget
from app.packer import ContextPacker, PackedMemories
from app.retrieval import MemoryHit, RetrievalResult
from app.scoring import score_hits, score_memory_hit


def pack_retrieval(
    result: RetrievalResult,
    budget: TokenBudget,
    *,
    packer: ContextPacker,
) -> PackedMemories:
    """Dedupe hot+cold by ``memory_id``, score, and pack under usable budget."""
    merged = _dedupe_hits(result.hot_memories + result.cold_memories)
    scored = score_hits(merged)
    return packer.pack(scored, budget.usable_budget)


def _dedupe_hits(hits: list[MemoryHit]) -> list[MemoryHit]:
    """Keep one hit per memory_id — prefer higher interim score, then lower rank."""
    best: dict[str, MemoryHit] = {}
    for hit in hits:
        existing = best.get(hit.memory_id)
        if existing is None:
            best[hit.memory_id] = hit
            continue
        if _prefer(hit, existing):
            best[hit.memory_id] = hit
    return list(best.values())


def _prefer(candidate: MemoryHit, incumbent: MemoryHit) -> bool:
    cand_score = score_memory_hit(candidate)
    inc_score = score_memory_hit(incumbent)
    if cand_score != inc_score:
        return cand_score > inc_score
    return candidate.rank < incumbent.rank
