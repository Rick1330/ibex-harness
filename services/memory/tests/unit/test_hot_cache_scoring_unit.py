"""Unit tests for hot cache scoring consistency (m3.D.3)."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from app.cache.hot_score import compute_hot_cache_score
from app.scoring import CompositeInputs, composite_score
from tests.unit.memory_test_support import sample_memory_row


def test_fresh_factual_outranks_stale_episodic_at_write_time() -> None:
    now = datetime(2026, 8, 29, tzinfo=UTC)
    factual = sample_memory_row(
        category="factual",
        valid_from=now - timedelta(days=90),
        usefulness_score=0.5,
        confidence=0.8,
        retrieval_count=2,
    )
    episodic = sample_memory_row(
        category="episodic",
        valid_from=now - timedelta(days=14),
        usefulness_score=0.5,
        confidence=0.8,
        retrieval_count=2,
    )
    factual_score = compute_hot_cache_score(factual, now=now)
    episodic_score = compute_hot_cache_score(episodic, now=now)
    assert factual_score > episodic_score


def test_score_orders_same_as_standalone_composite() -> None:
    now = datetime(2026, 8, 29, tzinfo=UTC)
    high = sample_memory_row(
        category="procedural",
        valid_from=now - timedelta(days=1),
        usefulness_score=0.9,
        confidence=0.95,
        retrieval_count=10,
    )
    low = sample_memory_row(
        category="episodic",
        valid_from=now - timedelta(days=30),
        usefulness_score=0.2,
        confidence=0.6,
        retrieval_count=0,
    )

    def expected(row):
        age = max(0.0, (now - row.valid_from).total_seconds() / 86400.0)
        return composite_score(
            CompositeInputs(
                relevance=1.0,
                age_days=age,
                categories=(row.category,),
                usefulness=float(row.usefulness_score),
                confidence=float(row.confidence),
                access_frequency=min(1.0, row.retrieval_count / 10.0),
            )
        )

    assert compute_hot_cache_score(high, now=now) == pytest.approx(expected(high))
    assert compute_hot_cache_score(low, now=now) == pytest.approx(expected(low))
    assert compute_hot_cache_score(high, now=now) > compute_hot_cache_score(low, now=now)
