"""Write-time hot cache composite score (shared with ZADD and tests)."""

from __future__ import annotations

from datetime import UTC, datetime

from app.scoring import CompositeInputs, composite_score
from app.write.models import MemoryRow


def compute_hot_cache_score(memory: MemoryRow, *, now: datetime | None = None) -> float:
    """Score for hot sorted set — relevance fixed at 1.0 (no query at write time)."""
    reference = now or datetime.now(tz=UTC)
    age_days = max(0.0, (reference - memory.valid_from).total_seconds() / 86400.0)
    return composite_score(
        CompositeInputs(
            relevance=1.0,
            age_days=age_days,
            categories=(memory.category,),
            usefulness=float(memory.usefulness_score),
            confidence=float(memory.confidence),
            access_frequency=min(1.0, memory.retrieval_count / 10.0),
        )
    )
