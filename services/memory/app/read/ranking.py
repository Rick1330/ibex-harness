"""Composite ranking for search read path (milestone 3.D.2 + 3.5.C.3 gate).

FTS supplemental hits have no cosine similarity. For composite scoring only we use a fixed
conservative relevance sentinel (0.5) so FTS rows rank below strong vector matches on the
relevance component while still competing on recency/confidence/usefulness. HTTP ``similarity``
remains the retrieval metric (cosine or raw ts_rank_cd).

Scoring-time relevance floor (ADR-0068): candidates whose composite relevance component is
below ``relevance_floor`` are excluded *before* ``composite_score``. This is distinct from
ADR-0053's retrieval-time ``min_similarity`` ANN cutoff. Keep ``relevance_floor`` strictly
below ``FTS_COMPOSITE_RELEVANCE`` so FTS hits are not mass-excluded.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Final
from uuid import UUID

from app.read.models import MemorySearchResult, SearchSource
from app.scoring import CompositeInputs, composite_score, passes_relevance_floor

FTS_COMPOSITE_RELEVANCE: Final[float] = 0.5

# Default matches Settings.composite_relevance_floor (ADR-0068 empirical pick).
DEFAULT_COMPOSITE_RELEVANCE_FLOOR: Final[float] = 0.15

_ACCESS_FREQUENCY_CAP = 10.0


@dataclass(frozen=True, slots=True)
class RankedCandidate:
    memory_id: UUID
    score: float
    source: SearchSource


@dataclass(frozen=True, slots=True)
class HydratedHit:
    """Hydrated row plus fields required for composite_score (not exposed on API)."""

    result: MemorySearchResult
    valid_from: datetime
    usefulness_score: float
    retrieval_count: int

    def composite_inputs(
        self,
        relevance: float,
        *,
        now: datetime | None = None,
    ) -> CompositeInputs:
        """Build CompositeInputs matching write hot-cache shape in cache.py::_write_hot."""
        reference = now or datetime.now(tz=UTC)
        valid_from = self.valid_from
        if valid_from.tzinfo is None:
            valid_from = valid_from.replace(tzinfo=UTC)
        age_days = max(0.0, (reference - valid_from).total_seconds() / 86400.0)
        return CompositeInputs(
            relevance=relevance,
            age_days=age_days,
            categories=(self.result.category,),
            usefulness=float(self.usefulness_score),
            confidence=float(self.result.confidence),
            access_frequency=min(1.0, self.retrieval_count / _ACCESS_FREQUENCY_CAP),
        )


def merge_candidates(
    vector: list[RankedCandidate],
    fts: list[RankedCandidate],
) -> list[RankedCandidate]:
    """Merge vector and FTS candidates; vector wins on duplicate memory_id."""
    by_id: dict[UUID, RankedCandidate] = {item.memory_id: item for item in vector}
    for item in fts:
        by_id.setdefault(item.memory_id, item)
    return list(by_id.values())


def relevance_for_composite(candidate: RankedCandidate) -> float:
    if candidate.source == "vector":
        return candidate.score
    return FTS_COMPOSITE_RELEVANCE


def rank_hydrated_hits(
    candidates: list[RankedCandidate],
    hydrated: dict[UUID, HydratedHit],
    *,
    now: datetime | None = None,
    relevance_floor: float = DEFAULT_COMPOSITE_RELEVANCE_FLOOR,
) -> list[MemorySearchResult]:
    """Sort by composite score descending; stable tie-break on memory_id.

    Candidates whose composite relevance is below ``relevance_floor`` are skipped
    (never scored). Empty input or all-below-floor yields an empty list.
    """
    reference = now or datetime.now(tz=UTC)
    scored: list[tuple[float, UUID, MemorySearchResult]] = []
    candidate_by_id = {item.memory_id: item for item in candidates}
    for memory_id, hit in hydrated.items():
        ranked = candidate_by_id.get(memory_id)
        if ranked is None:
            continue
        relevance = relevance_for_composite(ranked)
        if not passes_relevance_floor(relevance, relevance_floor):
            continue
        composite = composite_score(
            hit.composite_inputs(relevance, now=reference)
        )
        scored.append((composite, memory_id, hit.result))
    scored.sort(key=lambda item: (-item[0], str(item[1])))
    return [item[2] for item in scored]
