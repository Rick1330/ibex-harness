"""F4-029: Settings env → RankWeights mapping and production scoring wires."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, MagicMock
from uuid import UUID, uuid4

import pytest

from app.cache.hot_score import compute_hot_cache_score
from app.config import Settings
from app.read.models import FindSimilarQuery, MemorySearchResult
from app.read.ranking import HydratedHit
from app.read.repository import MemoryReadRepository
from app.vectorstore.base import SearchHit
from app.write.cache import MemoryCacheWriter
from app.write.models import WriteOutcome, WriteOutcomeKind
from tests.unit.memory_test_support import sample_memory_row

# Distinguishable weights that still sum to 1.0. Chosen so a field transposition
# in Settings.rank_weights() changes both RankWeights equality and ranking order.
_ENV_WEIGHTS = {
    "IBEX_RANK_WEIGHT_RELEVANCE": "0.10",
    "IBEX_RANK_WEIGHT_RECENCY": "0.20",
    "IBEX_RANK_WEIGHT_USEFULNESS": "0.30",
    "IBEX_RANK_WEIGHT_CONFIDENCE": "0.15",
    "IBEX_RANK_WEIGHT_FREQUENCY": "0.25",
}


def _settings_with_nondefault_weights(monkeypatch: pytest.MonkeyPatch) -> Settings:
    for key, value in _ENV_WEIGHTS.items():
        monkeypatch.setenv(key, value)
    return Settings(database_url="postgresql+asyncpg://x")


def _search_result(
    memory_id: UUID,
    *,
    similarity: float,
    org_id: UUID,
    agent_id: UUID,
) -> MemorySearchResult:
    now = datetime(2026, 8, 29, tzinfo=UTC)
    return MemorySearchResult(
        id=memory_id,
        org_id=org_id,
        agent_id=agent_id,
        content="content",
        category="factual",
        confidence=0.5,
        status="active",
        similarity=similarity,
        source="vector",
        created_at=now,
        updated_at=now,
    )


def test_settings_rank_weights_maps_env_fields_without_transposition(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Each IBEX_RANK_WEIGHT_* env var must land on the matching RankWeights field."""
    settings = _settings_with_nondefault_weights(monkeypatch)
    weights = settings.rank_weights()
    assert weights.relevance == pytest.approx(0.10)
    assert weights.recency == pytest.approx(0.20)
    assert weights.usefulness == pytest.approx(0.30)
    assert weights.confidence == pytest.approx(0.15)
    assert weights.frequency == pytest.approx(0.25)
    # Guard against pairwise swaps that still sum to 1.0.
    assert (weights.relevance, weights.recency, weights.usefulness) != (
        weights.recency,
        weights.relevance,
        weights.usefulness,
    )
    assert (weights.usefulness, weights.confidence, weights.frequency) != (
        weights.confidence,
        weights.usefulness,
        weights.frequency,
    )


@pytest.mark.asyncio
async def test_find_similar_uses_settings_rank_weights(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Production wire: MemoryReadRepository.find_similar must honor Settings weights."""
    settings = _settings_with_nondefault_weights(monkeypatch)
    org_id = uuid4()
    agent_id = uuid4()
    high_rel = uuid4()
    high_rec = uuid4()
    now = datetime(2026, 8, 29, tzinfo=UTC)

    store = MagicMock()
    store.search = AsyncMock(
        return_value=[
            SearchHit(memory_id=high_rel, similarity=0.95),
            SearchHit(memory_id=high_rec, similarity=0.50),
        ]
    )
    repo = MemoryReadRepository(MagicMock(), store, settings)

    def _hydrate(
        *,
        org_id: UUID,
        candidates: list,
        min_confidence: float,
    ) -> dict[UUID, HydratedHit]:
        del candidates, min_confidence
        return {
            high_rel: HydratedHit(
                result=_search_result(
                    high_rel, similarity=0.95, org_id=org_id, agent_id=agent_id
                ),
                valid_from=now - timedelta(days=100),
                usefulness_score=0.1,
                retrieval_count=0,
            ),
            high_rec: HydratedHit(
                result=_search_result(
                    high_rec, similarity=0.50, org_id=org_id, agent_id=agent_id
                ),
                valid_from=now,
                usefulness_score=0.1,
                retrieval_count=0,
            ),
        }

    repo._hydrate_hits = AsyncMock(side_effect=_hydrate)  # type: ignore[method-assign]

    ranked = await repo.find_similar(
        FindSimilarQuery(
            org_id=org_id,
            agent_id=agent_id,
            query_embedding=[0.0] * 1024,
            query_text="q",
            limit=2,
        )
    )
    # Defaults would put high_rel first; Settings weights flip to high_rec.
    assert ranked[0].id == high_rec
    assert ranked[1].id == high_rel


@pytest.mark.asyncio
async def test_cache_writer_hot_score_uses_settings_rank_weights(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Production wire: MemoryCacheWriter must ZADD the Settings-weighted score."""
    settings = _settings_with_nondefault_weights(monkeypatch)
    weights = settings.rank_weights()
    redis = MagicMock()
    script = AsyncMock(return_value=1)
    redis.register_script = MagicMock(return_value=script)
    redis.set = AsyncMock()
    writer = MemoryCacheWriter(redis, settings)
    # Use "now" as valid_from so age_days≈0 whether writer or helper call datetime.now.
    row = sample_memory_row(
        category="factual",
        valid_from=datetime.now(tz=UTC),
        usefulness_score=0.9,
        confidence=0.2,
        retrieval_count=10,
    )
    await writer.write_created(WriteOutcome(kind=WriteOutcomeKind.CREATED, memory=row))
    expected = compute_hot_cache_score(row, now=row.valid_from, weights=weights)
    defaulted = compute_hot_cache_score(row, now=row.valid_from)
    assert expected != pytest.approx(defaulted)
    call_args = script.await_args
    assert call_args is not None
    assert call_args.kwargs["args"][0] == pytest.approx(expected)
