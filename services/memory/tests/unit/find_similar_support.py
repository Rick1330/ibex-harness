"""Shared builders for find_similar unit tests (fallback, hybrid, and rerank)."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from unittest.mock import MagicMock
from uuid import UUID, uuid4

from app.config import Settings
from app.read.models import FindSimilarQuery, MemorySearchResult
from app.read.ranking import HydratedHit
from app.read.repository import MemoryReadRepository


def make_settings(**kwargs: object) -> Settings:
    return Settings(database_url="postgresql+asyncpg://x", **kwargs)


def make_result(
    memory_id: UUID,
    *,
    confidence: float = 0.9,
    source: str = "vector",
) -> MemorySearchResult:
    now = datetime.now(UTC)
    return MemorySearchResult(
        id=memory_id,
        org_id=uuid4(),
        agent_id=uuid4(),
        content="content",
        category="factual",
        confidence=confidence,
        status="active",
        similarity=0.95 if source == "vector" else 0.5,
        source=source,  # type: ignore[arg-type]
        created_at=now,
        updated_at=now,
    )


def make_hydrated_map(results: list[MemorySearchResult]) -> dict[UUID, HydratedHit]:
    now = datetime.now(UTC)
    return {
        item.id: HydratedHit(
            result=item,
            valid_from=now - timedelta(days=30),
            usefulness_score=0.5,
            retrieval_count=0,
        )
        for item in results
    }


def make_query(**kwargs: object) -> FindSimilarQuery:
    defaults: dict[str, object] = {
        "org_id": uuid4(),
        "agent_id": uuid4(),
        "query_embedding": [0.0] * 1024,
        "query_text": "q",
        "limit": 5,
    }
    defaults.update(kwargs)
    return FindSimilarQuery(**defaults)  # type: ignore[arg-type]


def make_repo(
    store: MagicMock | None = None,
    settings: Settings | None = None,
    *,
    rerank_client: object | None = None,
) -> MemoryReadRepository:
    return MemoryReadRepository(
        MagicMock(),
        store or MagicMock(),
        settings or make_settings(),
        rerank_client=rerank_client,  # type: ignore[arg-type]
    )
