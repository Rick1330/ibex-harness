from __future__ import annotations

import pytest
from pydantic import ValidationError

from app.config import Settings


def test_default_rank_weights_sum_to_one() -> None:
    settings = Settings()
    total = (
        settings.rank_weight_relevance
        + settings.rank_weight_recency
        + settings.rank_weight_usefulness
        + settings.rank_weight_confidence
        + settings.rank_weight_frequency
    )
    assert total == pytest.approx(1.0)
    assert settings.hnsw_ef_search == 40
    assert settings.vector_search_min_similarity == pytest.approx(0.70)
    assert settings.composite_relevance_floor == pytest.approx(0.15)


def test_composite_relevance_floor_from_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("IBEX_COMPOSITE_RELEVANCE_FLOOR", "0.20")
    settings = Settings()
    assert settings.composite_relevance_floor == pytest.approx(0.20)


def test_empty_database_url_becomes_none() -> None:
    settings = Settings(database_url="  ")
    assert settings.database_url is None


def test_rank_weights_must_sum_to_one(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("IBEX_RANK_WEIGHT_RELEVANCE", "0.50")
    monkeypatch.setenv("IBEX_RANK_WEIGHT_RECENCY", "0.50")
    monkeypatch.setenv("IBEX_RANK_WEIGHT_USEFULNESS", "0.50")
    monkeypatch.setenv("IBEX_RANK_WEIGHT_CONFIDENCE", "0.0")
    monkeypatch.setenv("IBEX_RANK_WEIGHT_FREQUENCY", "0.0")
    with pytest.raises(ValidationError):
        Settings()
