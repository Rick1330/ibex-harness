"""Shared builders for read-path ranking unit tests."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Literal
from uuid import UUID, uuid4

from app.read.models import MemorySearchResult
from app.read.ranking import HydratedHit, RankedCandidate, rank_hydrated_hits


@dataclass(frozen=True, slots=True)
class MemoryResultSeed:
    memory_id: UUID
    category: str = "factual"
    confidence: float = 0.8
    similarity: float = 0.9
    source: str = "vector"


@dataclass(frozen=True, slots=True)
class HydratedHitSeed:
    memory_id: UUID
    category: str = "factual"
    similarity: float = 0.9
    source: str = "vector"
    age_days: float = 1.0
    usefulness: float = 0.5
    confidence: float = 0.8
    retrieval_count: int = 0


def memory_search_result(
    seed: MemoryResultSeed,
    *,
    now: datetime | None = None,
) -> MemorySearchResult:
    reference = now or datetime.now(UTC)
    return MemorySearchResult(
        id=seed.memory_id,
        org_id=uuid4(),
        agent_id=uuid4(),
        content="content",
        category=seed.category,
        confidence=seed.confidence,
        status="active",
        similarity=seed.similarity,
        source=seed.source,  # type: ignore[arg-type]
        created_at=reference,
        updated_at=reference,
    )


def hydrated_hit(
    seed: HydratedHitSeed,
    *,
    now: datetime | None = None,
) -> HydratedHit:
    """Build a hit whose ``valid_from`` is ``now - age_days``.

    Callers that pass a fixed ``now`` into ``rank_hydrated_hits`` must pass the
    same reference here; otherwise wall-clock drift vs the fixed rank clock
    silently changes ages and can invert category half-life ordering.
    """
    reference = now or datetime.now(UTC)
    return HydratedHit(
        result=memory_search_result(
            MemoryResultSeed(
                memory_id=seed.memory_id,
                category=seed.category,
                confidence=seed.confidence,
                similarity=seed.similarity,
                source=seed.source,
            ),
            now=reference,
        ),
        valid_from=reference - timedelta(days=seed.age_days),
        usefulness_score=seed.usefulness,
        retrieval_count=seed.retrieval_count,
    )


@dataclass(frozen=True, slots=True)
class RankScenario:
    candidates: tuple[RankedCandidate, ...]
    hydrated: dict[UUID, HydratedHit]
    expected_first: UUID
    fixed_now: datetime
    expect_first_similarity_higher: bool = False
    expect_similarity_inverted: bool = False


def assert_first_ranked(scenario: RankScenario) -> None:
    ranked = rank_hydrated_hits(
        list(scenario.candidates),
        scenario.hydrated,
        now=scenario.fixed_now,
    )
    assert ranked[0].id == scenario.expected_first
    if scenario.expect_first_similarity_higher:
        assert ranked[0].similarity > ranked[1].similarity
    if scenario.expect_similarity_inverted:
        assert ranked[0].similarity < ranked[1].similarity


_FIXED_RANK_NOW = datetime(2026, 8, 29, tzinfo=UTC)


@dataclass(frozen=True, slots=True)
class EpisodicVectorFtsSeed:
    vector_retrieval_score: float
    fts_retrieval_score: float
    vector_similarity: float
    fts_similarity: float
    age_days: float = 1.0
    usefulness: float = 0.5
    confidence: float = 0.8
    retrieval_count: int = 0
    expected_winner: Literal["vector", "fts"] = "vector"
    expect_similarity_inverted: bool = False
    expect_first_similarity_higher: bool = False
    vector_age_days: float | None = None
    fts_age_days: float | None = None
    vector_usefulness: float | None = None
    fts_usefulness: float | None = None
    vector_confidence: float | None = None
    fts_confidence: float | None = None
    vector_retrieval_count: int | None = None
    fts_retrieval_count: int | None = None


def episodic_vector_fts_scenario(seed: EpisodicVectorFtsSeed) -> RankScenario:
    vector_id = uuid4()
    fts_id = uuid4()

    def _hit(
        memory_id: UUID,
        *,
        similarity: float,
        source: str,
        age_days: float,
        usefulness: float,
        confidence: float,
        retrieval_count: int,
    ) -> HydratedHit:
        return hydrated_hit(
            HydratedHitSeed(
                memory_id=memory_id,
                category="episodic",
                similarity=similarity,
                source=source,
                age_days=age_days,
                usefulness=usefulness,
                confidence=confidence,
                retrieval_count=retrieval_count,
            ),
            now=_FIXED_RANK_NOW,
        )

    vector_hit = _hit(
        vector_id,
        similarity=seed.vector_similarity,
        source="vector",
        age_days=seed.vector_age_days if seed.vector_age_days is not None else seed.age_days,
        usefulness=seed.vector_usefulness if seed.vector_usefulness is not None else seed.usefulness,
        confidence=seed.vector_confidence if seed.vector_confidence is not None else seed.confidence,
        retrieval_count=(
            seed.vector_retrieval_count
            if seed.vector_retrieval_count is not None
            else seed.retrieval_count
        ),
    )
    fts_hit = _hit(
        fts_id,
        similarity=seed.fts_similarity,
        source="full_text",
        age_days=seed.fts_age_days if seed.fts_age_days is not None else seed.age_days,
        usefulness=seed.fts_usefulness if seed.fts_usefulness is not None else seed.usefulness,
        confidence=seed.fts_confidence if seed.fts_confidence is not None else seed.confidence,
        retrieval_count=(
            seed.fts_retrieval_count if seed.fts_retrieval_count is not None else seed.retrieval_count
        ),
    )
    expected_first = vector_id if seed.expected_winner == "vector" else fts_id
    return RankScenario(
        candidates=(
            RankedCandidate(memory_id=fts_id, score=seed.fts_retrieval_score, source="full_text"),
            RankedCandidate(memory_id=vector_id, score=seed.vector_retrieval_score, source="vector"),
        ),
        hydrated={fts_id: fts_hit, vector_id: vector_hit},
        expected_first=expected_first,
        fixed_now=_FIXED_RANK_NOW,
        expect_similarity_inverted=seed.expect_similarity_inverted,
        expect_first_similarity_higher=seed.expect_first_similarity_higher,
    )


def factual_beats_episodic_scenario() -> RankScenario:
    factual_id = uuid4()
    episodic_id = uuid4()
    return RankScenario(
        candidates=(
            RankedCandidate(memory_id=episodic_id, score=0.90, source="vector"),
            RankedCandidate(memory_id=factual_id, score=0.90, source="vector"),
        ),
        hydrated={
            episodic_id: hydrated_hit(
                HydratedHitSeed(
                    memory_id=episodic_id,
                    category="episodic",
                    similarity=0.90,
                    age_days=14.0,
                ),
                now=_FIXED_RANK_NOW,
            ),
            factual_id: hydrated_hit(
                HydratedHitSeed(
                    memory_id=factual_id,
                    category="factual",
                    similarity=0.90,
                    age_days=90.0,
                ),
                now=_FIXED_RANK_NOW,
            ),
        },
        expected_first=factual_id,
        fixed_now=_FIXED_RANK_NOW,
    )


def vector_beats_fts_scenario() -> RankScenario:
    return episodic_vector_fts_scenario(
        EpisodicVectorFtsSeed(
            vector_retrieval_score=0.85,
            fts_retrieval_score=0.9,
            vector_similarity=0.85,
            fts_similarity=0.9,
        )
    )


def sentinel_boundary_weak_vector_beats_fts_scenario() -> RankScenario:
    """FTS sentinel (0.5) must not outrank a weak vector hit when metadata is equal."""
    return episodic_vector_fts_scenario(
        EpisodicVectorFtsSeed(
            vector_retrieval_score=0.51,
            fts_retrieval_score=0.99,
            vector_similarity=0.51,
            fts_similarity=0.99,
            age_days=7.0,
            retrieval_count=2,
            expect_similarity_inverted=True,
        )
    )


def fts_outranks_stale_weak_vector_scenario() -> RankScenario:
    """Fresh FTS may outrank a stale weak vector when recency/usefulness dominate."""
    return episodic_vector_fts_scenario(
        EpisodicVectorFtsSeed(
            vector_retrieval_score=0.52,
            fts_retrieval_score=0.95,
            vector_similarity=0.52,
            fts_similarity=0.95,
            expected_winner="fts",
            expect_first_similarity_higher=True,
            vector_age_days=120.0,
            fts_age_days=1.0,
            vector_usefulness=0.2,
            fts_usefulness=0.9,
            vector_confidence=0.7,
            fts_confidence=0.9,
            vector_retrieval_count=0,
            fts_retrieval_count=5,
        )
    )
