"""Composite ranking for search read path (milestone 3.D.2 + 3.5.C.3 gate).

FTS supplemental hits have no cosine similarity. For composite scoring only we use a fixed
conservative relevance sentinel (0.5) so FTS rows rank below strong vector matches on the
relevance component while still competing on recency/confidence/usefulness. HTTP ``similarity``
remains the retrieval metric (cosine similarity, or FTS ``ts_rank_cd`` clamped to ``[0, 1]``).

Scoring-time relevance floor (ADR-0068): candidates whose composite relevance component is
below ``relevance_floor`` are excluded *before* ``composite_score``. This is distinct from
ADR-0053's retrieval-time ``min_similarity`` ANN cutoff. Settings require
``relevance_floor`` ``< 0.5`` (FTS sentinel); gate semantics exclude FTS only when
floor ``> 0.5``.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Final
from uuid import UUID

from app.read.fusion import RRF_K_DEFAULT, reciprocal_rank_fusion
from app.read.models import MemorySearchResult, SearchSource
from app.scoring import CompositeInputs, RankWeights, composite_score, passes_relevance_floor

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
        categories = (
            self.result.categories
            if self.result.categories
            else (self.result.category,)
        )
        return CompositeInputs(
            relevance=relevance,
            age_days=age_days,
            categories=categories,
            usefulness=float(self.usefulness_score),
            confidence=float(self.result.confidence),
            access_frequency=min(1.0, self.retrieval_count / _ACCESS_FREQUENCY_CAP),
        )


@dataclass(frozen=True, slots=True)
class RankOptions:
    """Optional knobs for ``rank_hydrated_hits`` (keeps public arity ≤ 3)."""

    now: datetime | None = None
    relevance_floor: float = DEFAULT_COMPOSITE_RELEVANCE_FLOOR
    weights: RankWeights | None = None
    #: Per-memory relevance that overrides the retrieval score (cross-encoder rerank).
    relevance_overrides: Mapping[UUID, float] | None = None


def merge_candidates(
    vector: list[RankedCandidate],
    fts: list[RankedCandidate],
) -> list[RankedCandidate]:
    """Merge vector and FTS candidates; vector wins on duplicate memory_id."""
    by_id: dict[UUID, RankedCandidate] = {item.memory_id: item for item in vector}
    for item in fts:
        by_id.setdefault(item.memory_id, item)
    return list(by_id.values())


def fuse_candidates(
    vector: list[RankedCandidate],
    fts: list[RankedCandidate],
    *,
    k: int = RRF_K_DEFAULT,
) -> list[RankedCandidate]:
    """Order the union of both channels by reciprocal rank fusion.

    The candidate keeps its own channel score: cosine for a vector hit, clamped
    ``ts_rank_cd`` for a full-text hit. Fusion decides *which* candidates are
    admitted and in what order; composite scoring still decides the presentation
    order, so ADR-0068 weights and floors keep their meaning.

    The returned list is the whole fused union. The caller windows it to the page
    size before hydration, which is what makes fusion decide admission rather
    than merely decorate an ordering that composite score overrides.
    """
    by_id: dict[UUID, RankedCandidate] = {}
    for item in [*vector, *fts]:
        # Vector wins a duplicate: its score is the one composite scoring uses.
        by_id.setdefault(item.memory_id, item)
    ordering = reciprocal_rank_fusion(
        [[item.memory_id for item in vector], [item.memory_id for item in fts]],
        k=k,
    )
    return [by_id[item.memory_id] for item in ordering]


def relevance_for_composite(candidate: RankedCandidate) -> float:
    if candidate.source == "vector":
        return candidate.score
    return FTS_COMPOSITE_RELEVANCE


def _relevance_for(candidate: RankedCandidate, opts: RankOptions) -> float:
    """Rerank score when one exists, else the candidate's own retrieval score.

    TEI returns a normalized ``[0, 1]`` score for a reranker, so it is directly the
    composite relevance component. The clamp is defensive: a composite input outside
    the unit interval is a contract violation, and dropping the whole page over it
    would be worse than saturating the component.
    """
    overrides = opts.relevance_overrides
    if overrides is None:
        return relevance_for_composite(candidate)
    override = overrides.get(candidate.memory_id)
    if override is None:
        return relevance_for_composite(candidate)
    return min(1.0, max(0.0, override))


def rank_hydrated_hits(
    candidates: list[RankedCandidate],
    hydrated: dict[UUID, HydratedHit],
    options: RankOptions | None = None,
) -> list[MemorySearchResult]:
    """Sort by composite score descending; stable tie-break on memory_id.

    Candidates whose composite relevance is below ``relevance_floor`` are skipped
    (never scored). Empty input or all-below-floor yields an empty list.
    """
    opts = options or RankOptions()
    reference = opts.now or datetime.now(tz=UTC)
    scored: list[tuple[float, UUID, MemorySearchResult]] = []
    candidate_by_id = {item.memory_id: item for item in candidates}
    for memory_id, hit in hydrated.items():
        ranked = candidate_by_id.get(memory_id)
        if ranked is None:
            continue
        relevance = _relevance_for(ranked, opts)
        if not passes_relevance_floor(relevance, opts.relevance_floor):
            continue
        composite = composite_score(
            hit.composite_inputs(relevance, now=reference),
            opts.weights,
        )
        scored.append((composite, memory_id, hit.result))
    scored.sort(key=lambda item: (-item[0], str(item[1])))
    return [item[2] for item in scored]
