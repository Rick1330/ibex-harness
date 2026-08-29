"""Unit tests for POST /v1/memories/search router."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.exc import DBAPIError

from app.auth.client import StaticTokenValidator, ValidateResult
from app.clients.embedding import EmbeddingClientError
from app.config import Settings
from app.deps import get_embedding_client, get_read_repository
from app.main import create_app
from app.permissions import MEMORY_READ, MEMORY_WRITE
from app.read.models import MemorySearchResult
from tests.unit.memory_test_support import sample_memory_row

ORG = uuid4()
AGENT = uuid4()
TOKEN = "search-router-token"


def _search(http: TestClient, *, query: str = "dark mode", limit: int = 5):
    return http.post(
        "/v1/memories/search",
        headers={"Authorization": f"Bearer {TOKEN}"},
        json={
            "agent_id": str(AGENT),
            "query": query,
            "limit": limit,
            "min_similarity": 0.0,
        },
    )


@pytest.fixture
def client() -> tuple[TestClient, AsyncMock, MagicMock]:
    settings = Settings(
        database_url="postgresql+asyncpg://ibex:ibex@127.0.0.1:5432/ibex",
        embedding_api_token="unit-test-token",
    )
    validator = StaticTokenValidator(
        {TOKEN: ValidateResult(org_id=ORG, permissions=MEMORY_READ, agent_id=AGENT)}
    )
    app = create_app(settings=settings, validator=validator)
    mock_repo = AsyncMock()
    mock_embed = MagicMock()
    mock_embed.embed = AsyncMock(
        return_value=MagicMock(vectors=[[0.1] * 1024], model_id="m", dimensions=1024)
    )
    app.dependency_overrides[get_read_repository] = lambda: mock_repo
    app.dependency_overrides[get_embedding_client] = lambda: mock_embed
    return TestClient(app), mock_repo, mock_embed


def test_search_memories_200(client) -> None:
    http, mock_repo, _ = client
    row = sample_memory_row(org_id=ORG, agent_id=AGENT, content="dark mode")
    mock_repo.find_similar = AsyncMock(
        return_value=[
            MemorySearchResult(
                id=row.id,
                org_id=ORG,
                agent_id=AGENT,
                content=row.content,
                category=row.category,
                confidence=row.confidence,
                status=row.status,
                similarity=0.92,
                source="vector",
                created_at=row.created_at,
                updated_at=row.updated_at,
            )
        ]
    )
    with http:
        resp = _search(http)
    assert resp.status_code == 200
    body = resp.json()
    assert body["data"]["results"][0]["rank"] == 1
    assert body["data"]["results"][0]["source"] == "vector"


def test_search_memories_403_without_read_permission() -> None:
    settings = Settings(
        database_url="postgresql+asyncpg://ibex:ibex@127.0.0.1:5432/ibex",
        embedding_api_token="unit-test-token",
    )
    validator = StaticTokenValidator(
        {TOKEN: ValidateResult(org_id=ORG, permissions=MEMORY_WRITE, agent_id=AGENT)}
    )
    app = create_app(settings=settings, validator=validator)
    with TestClient(app) as http:
        resp = _search(http)
    assert resp.status_code == 403


def test_search_memories_403_agent_mismatch() -> None:
    other_agent = uuid4()
    settings = Settings(
        database_url="postgresql+asyncpg://ibex:ibex@127.0.0.1:5432/ibex",
        embedding_api_token="unit-test-token",
    )
    validator = StaticTokenValidator(
        {TOKEN: ValidateResult(org_id=ORG, permissions=MEMORY_READ, agent_id=AGENT)}
    )
    app = create_app(settings=settings, validator=validator)
    with TestClient(app) as http:
        resp = http.post(
            "/v1/memories/search",
            headers={"Authorization": f"Bearer {TOKEN}"},
            json={
                "agent_id": str(other_agent),
                "query": "dark mode",
                "limit": 5,
                "min_similarity": 0.0,
            },
        )
    assert resp.status_code == 403
    assert resp.json()["detail"]["code"] == "AGENT_NOT_AUTHORIZED"


def test_search_memories_503_embedding_failure(client) -> None:
    http, mock_repo, mock_embed = client
    mock_repo.find_similar = AsyncMock(return_value=[])
    mock_embed.embed = AsyncMock(side_effect=EmbeddingClientError("down"))
    with http:
        resp = _search(http)
    assert resp.status_code == 503
    assert resp.json()["detail"]["code"] == "EMBEDDING_FAILED"


def test_search_memories_503_database_failure(client) -> None:
    http, mock_repo, _ = client
    mock_repo.find_similar = AsyncMock(
        side_effect=DBAPIError("stmt", {}, Exception("db down"))
    )
    with http:
        resp = _search(http)
    assert resp.status_code == 503
    assert resp.json()["detail"]["code"] == "DATABASE_UNAVAILABLE"
