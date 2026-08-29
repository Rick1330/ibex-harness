"""Latency smoke for isolated composite ranking (milestone 3.D.2 pre-merge gate)."""

from __future__ import annotations

import time
from datetime import UTC, datetime
from uuid import uuid4

from app.read.ranking import RankedCandidate, rank_hydrated_hits
from tests.unit.read_ranking_support import HydratedHitSeed, hydrated_hit

_WARMUP_ITERATIONS = 20
_TIMED_ITERATIONS = 200
_CANDIDATE_COUNT = 70
_P50_BUDGET_MS = 5.0
_P95_BUDGET_MS = 10.0


def _percentile_ms(samples_ms: list[float], percentile: float) -> float:
    ordered = sorted(samples_ms)
    index = max(0, int(len(ordered) * percentile) - 1)
    return ordered[index]


def _build_ranking_fixture(candidate_count: int) -> tuple[list[RankedCandidate], dict]:
    fixed_now = datetime(2026, 8, 29, 12, 0, tzinfo=UTC)
    candidates: list[RankedCandidate] = []
    hydrated = {}
    for index in range(candidate_count):
        memory_id = uuid4()
        source = "vector" if index % 5 else "full_text"
        similarity = 0.55 + (index % 40) * 0.01
        candidates.append(
            RankedCandidate(
                memory_id=memory_id,
                score=similarity,
                source=source,  # type: ignore[arg-type]
            )
        )
        hydrated[memory_id] = hydrated_hit(
            HydratedHitSeed(
                memory_id=memory_id,
                category="factual" if index % 2 == 0 else "episodic",
                similarity=similarity,
                source=source,
                age_days=float(index % 90) + 1.0,
                usefulness=0.4 + (index % 5) * 0.1,
                confidence=0.7 + (index % 3) * 0.05,
                retrieval_count=index % 10,
            )
        )
    return candidates, hydrated, fixed_now


def test_rank_hydrated_hits_latency_at_70_candidates() -> None:
    """Isolated composite scoring p95 must stay within the 70-candidate budget."""
    candidates, hydrated, fixed_now = _build_ranking_fixture(_CANDIDATE_COUNT)

    for _ in range(_WARMUP_ITERATIONS):
        rank_hydrated_hits(candidates, hydrated, now=fixed_now)

    samples_ms: list[float] = []
    for _ in range(_TIMED_ITERATIONS):
        start = time.perf_counter()
        ranked = rank_hydrated_hits(candidates, hydrated, now=fixed_now)
        samples_ms.append((time.perf_counter() - start) * 1000)
        assert len(ranked) == _CANDIDATE_COUNT

    p50 = _percentile_ms(samples_ms, 0.50)
    p95 = _percentile_ms(samples_ms, 0.95)

    # Printed for pre-merge PR evidence (Step 1); assertion enforces budget in CI.
    print(
        f"composite_ranking_latency candidates={_CANDIDATE_COUNT} "
        f"p50_ms={p50:.3f} p95_ms={p95:.3f} iterations={_TIMED_ITERATIONS}"
    )

    assert p50 < _P50_BUDGET_MS, f"composite ranking p50 {p50:.3f}ms exceeds {_P50_BUDGET_MS}ms"
    assert p95 < _P95_BUDGET_MS, f"composite ranking p95 {p95:.3f}ms exceeds {_P95_BUDGET_MS}ms"
