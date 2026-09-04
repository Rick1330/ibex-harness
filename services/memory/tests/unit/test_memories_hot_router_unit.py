"""Unit tests for GET /v1/memories/hot router (milestone 3.5.C.2)."""

from __future__ import annotations

import math
from datetime import UTC, datetime
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from app.auth.client import StaticTokenValidator, ValidateResult
from app.config import Settings
from app.deps import get_hot_cache_reader
from app.main import create_app
from app.permissions import MEMORY_READ, MEMORY_WRITE
from app.read.models import HotMemoryQuery, MemorySearchResult
from tests.unit.memory_test_support import sample_memory_row

ORG = uuid4()
OTHER_ORG = uuid4()
AGENT = uuid4()
TOKEN = "hot-router-token"


def _hot(http: TestClient, *, agent_id=AGENT, limit: int = 20, min_confidence: float = 0.0):
    return http.get(
        "/v1/memories/hot",
        headers={"Authorization": f"Bearer {TOKEN}"},
        params={
            "agent_id": str(agent_id),
            "limit": limit,
            "min_confidence": min_confidence,
        },
    )


@pytest.fixture
def client(monkeypatch) -> tuple[TestClient, AsyncMock]:
    settings = Settings(
        database_url="postgresql+asyncpg://ibex:ibex@127.0.0.1:5432/ibex",
        embedding_api_token="unit-test-token",
    )
    validator = StaticTokenValidator(
        {TOKEN: ValidateResult(org_id=ORG, permissions=MEMORY_READ, agent_id=AGENT)}
    )
    app = create_app(settings=settings, validator=validator)
    mock_reader = AsyncMock()
    app.dependency_overrides[get_hot_cache_reader] = lambda: mock_reader

    async def _skip_agent_org_check(*_args, **_kwargs) -> None:
        return None

    monkeypatch.setattr(
        "app.routers.memories.ensure_search_agent_authorized",
        _skip_agent_org_check,
    )
    return TestClient(app), mock_reader


def test_list_hot_memories_200(client) -> None:
    http, mock_reader = client
    row = sample_memory_row(org_id=ORG, agent_id=AGENT, content="prefer dark mode")
    mock_reader.get_hot_memories = AsyncMock(
        return_value=[
            MemorySearchResult(
                id=row.id,
                org_id=ORG,
                agent_id=AGENT,
                content=row.content,
                category=row.category,
                confidence=row.confidence,
                status=row.status,
                similarity=0.81,
                source="hot_cache",
                created_at=row.created_at,
                updated_at=row.updated_at,
            )
        ]
    )
    with http:
        resp = _hot(http)
    assert resp.status_code == 200
    body = resp.json()
    hit = body["data"]["results"][0]
    assert hit["rank"] == 1
    assert hit["source"] == "hot_cache"
    assert hit["memory"]["content"] == "prefer dark mode"
    query: HotMemoryQuery = mock_reader.get_hot_memories.await_args.args[0]
    assert query.org_id == ORG
    assert query.agent_id == AGENT
    assert query.limit == 20


def test_list_hot_memories_scopes_org_from_token(client) -> None:
    """Token org is passed to the reader — never the caller's guessed org."""
    http, mock_reader = client
    mock_reader.get_hot_memories = AsyncMock(return_value=[])
    with http:
        resp = _hot(http)
    assert resp.status_code == 200
    query: HotMemoryQuery = mock_reader.get_hot_memories.await_args.args[0]
    assert query.org_id == ORG
    assert query.org_id != OTHER_ORG


def _app_with_token(*, permissions: int, agent_id=AGENT) -> TestClient:
    settings = Settings(
        database_url="postgresql+asyncpg://ibex:ibex@127.0.0.1:5432/ibex",
        embedding_api_token="unit-test-token",
    )
    validator = StaticTokenValidator(
        {TOKEN: ValidateResult(org_id=ORG, permissions=permissions, agent_id=agent_id)}
    )
    return TestClient(create_app(settings=settings, validator=validator))


def test_list_hot_memories_403_without_read_permission() -> None:
    with _app_with_token(permissions=MEMORY_WRITE) as http:
        resp = _hot(http)
    assert resp.status_code == 403


def test_list_hot_memories_403_agent_mismatch() -> None:
    other_agent = uuid4()
    with _app_with_token(permissions=MEMORY_READ) as http:
        resp = _hot(http, agent_id=other_agent)
    assert resp.status_code == 403
    assert resp.json()["detail"]["code"] == "AGENT_NOT_AUTHORIZED"


def test_list_hot_memories_401_missing_token() -> None:
    with _app_with_token(permissions=MEMORY_READ) as http:
        resp = http.get("/v1/memories/hot", params={"agent_id": str(AGENT)})
    assert resp.status_code == 401


def test_list_hot_memories_empty_ok(client) -> None:
    http, mock_reader = client
    mock_reader.get_hot_memories = AsyncMock(return_value=[])
    with http:
        resp = _hot(http)
    assert resp.status_code == 200
    assert resp.json()["data"]["results"] == []


def test_list_hot_memories_400_on_value_error(client) -> None:
    http, mock_reader = client
    mock_reader.get_hot_memories = AsyncMock(side_effect=ValueError("limit must be >= 1"))
    with http:
        resp = _hot(http)
    assert resp.status_code == 400


def test_list_hot_memories_503_on_database_error(client) -> None:
    from sqlalchemy.exc import DBAPIError

    http, mock_reader = client
    mock_reader.get_hot_memories = AsyncMock(
        side_effect=DBAPIError("stmt", {}, Exception("db down"))
    )
    with http:
        resp = _hot(http)
    assert resp.status_code == 503
    assert resp.json()["detail"]["code"] == "DATABASE_UNAVAILABLE"


def test_list_hot_http_latency_overhead_bounded(client) -> None:
    """HTTP layer overhead over mocked reader must stay small (ASGI + JSON).

    In-process hot-cache p99 gate remains <5ms elsewhere; this asserts the
    router wrapper does not add pathological latency under mocked I/O.
    """
    import time

    http, mock_reader = client
    now = datetime.now(tz=UTC)
    rows = [
        MemorySearchResult(
            id=uuid4(),
            org_id=ORG,
            agent_id=AGENT,
            content="cached",
            category="factual",
            confidence=0.9,
            status="active",
            similarity=0.7,
            source="hot_cache",
            created_at=now,
            updated_at=now,
        )
        for _ in range(20)
    ]
    mock_reader.get_hot_memories = AsyncMock(return_value=rows)

    warmup = 10
    timed = 50
    with http:
        for _ in range(warmup):
            assert _hot(http).status_code == 200
        samples_ms: list[float] = []
        for _ in range(timed):
            start = time.perf_counter()
            assert _hot(http).status_code == 200
            samples_ms.append((time.perf_counter() - start) * 1000.0)
    ordered = sorted(samples_ms)
    p99 = ordered[max(0, math.ceil(len(ordered) * 0.99) - 1)]
    # Nearest-rank p99 on n=50 is the max sample; keep a generous TestClient budget.
    assert p99 < 100.0, f"hot HTTP p99={p99:.2f}ms exceeded 100ms mock budget"
