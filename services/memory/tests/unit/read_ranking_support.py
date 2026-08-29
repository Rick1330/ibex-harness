"""Shared builders for read-path ranking unit tests."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
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


def memory_search_result(seed: MemoryResultSeed) -> MemorySearchResult:
    now = datetime.now(UTC)
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
        created_at=now,
        updated_at=now,
    )


def hydrated_hit(seed: HydratedHitSeed) -> HydratedHit:
    now = datetime.now(UTC)
    return HydratedHit(
        result=memory_search_result(
            MemoryResultSeed(
                memory_id=seed.memory_id,
                category=seed.category,
                confidence=seed.confidence,
                similarity=seed.similarity,
                source=seed.source,
            )
        ),
        valid_from=now - timedelta(days=seed.age_days),
        usefulness_score=seed.usefulness,
        retrieval_count=seed.retrieval_count,
    )


@dataclass(frozen=True, slots=True)
class RankScenario:
    candidates: tuple[RankedCandidate, ...]
    hydrated: dict[UUID, HydratedHit]
    expected_first: UUID
    fixed_now: datetime


def assert_first_ranked(scenario: RankScenario) -> None:
    ranked = rank_hydrated_hits(
        list(scenario.candidates),
        scenario.hydrated,
        now=scenario.fixed_now,
    )
    assert ranked[0].id == scenario.expected_first
