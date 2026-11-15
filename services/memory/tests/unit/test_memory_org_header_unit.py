"""X-Ibex-Org-Id handling on the memory read surfaces (S05 / T1.5).

Context assembly sends the org it is assembling for. Memory still derives the
tenant from the validated token; the header is a check that turns a mismatch
into a 403 *before* any read, instead of silently answering for the token's org.

The point of these tests is the refusal and the absence of a read, not the
presence of a header.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from app.auth.client import StaticTokenValidator, ValidateResult
from app.config import Settings
from app.deps import ORG_HEADER, get_embedding_client, get_hot_cache_reader, get_read_repository
from app.main import create_app
from app.permissions import MEMORY_READ
from app.read.models import MemorySearchResult
from tests.unit.memory_test_support import sample_memory_row

ORG = uuid4()
OTHER_ORG = uuid4()
AGENT = uuid4()
TOKEN = "org-header-token"


def _app(monkeypatch, *, hot_reader: AsyncMock | None = None) -> TestClient:
    settings = Settings(
        database_url="postgresql+asyncpg://ibex:ibex@127.0.0.1:5432/ibex",
        embedding_api_token="unit-test-token",
    )
    validator = StaticTokenValidator(
        {TOKEN: ValidateResult(org_id=ORG, permissions=MEMORY_READ, agent_id=AGENT)}
    )
    app = create_app(settings=settings, validator=validator)

    async def _skip_agent_org_check(*_args, **_kwargs) -> None:
        return None

    monkeypatch.setattr(
        "app.routers.memories.ensure_search_agent_authorized",
        _skip_agent_org_check,
    )
    if hot_reader is not None:
        app.dependency_overrides[get_hot_cache_reader] = lambda: hot_reader
    return TestClient(app)


def _headers(org_id: object | None) -> dict[str, str]:
    headers = {"Authorization": f"Bearer {TOKEN}"}
    if org_id is not None:
        headers[ORG_HEADER] = str(org_id)
    return headers


def _search(http: TestClient, *, org_id: object | None):
    return http.post(
        "/v1/memories/search",
        headers=_headers(org_id),
        json={"agent_id": str(AGENT), "query": "dark mode", "limit": 5},
    )


def _hot(http: TestClient, *, org_id: object | None):
    return http.get(
        "/v1/memories/hot",
        headers=_headers(org_id),
        params={"agent_id": str(AGENT), "limit": 20},
    )


def _search_app(monkeypatch) -> tuple[TestClient, AsyncMock, MagicMock]:
    http = _app(monkeypatch)
    repo = AsyncMock()
    embed = MagicMock()
    embed.embed = AsyncMock(
        return_value=MagicMock(vectors=[[0.1] * 1024], model_id="m", dimensions=1024)
    )
    repo.find_similar = AsyncMock(return_value=[])
    http.app.dependency_overrides[get_read_repository] = lambda: repo
    http.app.dependency_overrides[get_embedding_client] = lambda: embed
    return http, repo, embed


def _assert_refused_without_leaking(resp, *, other_org: object) -> None:
    """403, no results envelope, and nothing about the named org."""
    assert resp.status_code == 403
    body = resp.json()
    assert body["detail"]["code"] == "ORG_MISMATCH"
    assert set(body) == {"detail"}
    assert "results" not in body
    assert "memories" not in body
    assert str(other_org) not in resp.text


def test_search_matching_org_header_is_unchanged(monkeypatch) -> None:
    http, repo, embed = _search_app(monkeypatch)
    row = sample_memory_row(org_id=ORG, agent_id=AGENT, content="dark mode")
    repo.find_similar = AsyncMock(
        return_value=[
            MemorySearchResult(
                id=row.id,
                org_id=ORG,
                agent_id=AGENT,
                content=row.content,
                category=row.category,
                confidence=row.confidence,
                status=row.status,
                similarity=0.9,
                source="vector",
                created_at=row.created_at,
                updated_at=row.updated_at,
            )
        ]
    )
    with http:
        resp = _search(http, org_id=ORG)
    assert resp.status_code == 200
    assert resp.json()["data"]["results"][0]["memory"]["content"] == "dark mode"
    query = repo.find_similar.await_args.args[0]
    assert query.org_id == ORG
    embed.embed.assert_awaited()


def test_search_other_org_header_403_before_any_read(monkeypatch) -> None:
    http, repo, embed = _search_app(monkeypatch)
    with http:
        resp = _search(http, org_id=OTHER_ORG)
    _assert_refused_without_leaking(resp, other_org=OTHER_ORG)
    # No read: no embedding call, no similarity query. The refusal is the answer.
    embed.embed.assert_not_awaited()
    repo.find_similar.assert_not_awaited()


def test_search_missing_org_header_uses_token_org(monkeypatch) -> None:
    """Absent header is the token's org — an older context keeps working."""
    http, repo, _embed = _search_app(monkeypatch)
    with http:
        resp = _search(http, org_id=None)
    assert resp.status_code == 200
    query = repo.find_similar.await_args.args[0]
    assert query.org_id == ORG


def test_search_malformed_org_header_400(monkeypatch) -> None:
    http, repo, embed = _search_app(monkeypatch)
    with http:
        resp = _search(http, org_id="not-a-uuid")
    assert resp.status_code == 400
    assert resp.json()["detail"]["code"] == "INVALID_ORG_HEADER"
    embed.embed.assert_not_awaited()
    repo.find_similar.assert_not_awaited()


def test_hot_matching_org_header_is_unchanged(monkeypatch) -> None:
    reader = AsyncMock()
    reader.get_hot_memories = AsyncMock(return_value=[])
    http = _app(monkeypatch, hot_reader=reader)
    with http:
        resp = _hot(http, org_id=ORG)
    assert resp.status_code == 200
    query = reader.get_hot_memories.await_args.args[0]
    assert query.org_id == ORG


def test_hot_other_org_header_403_before_any_read(monkeypatch) -> None:
    reader = AsyncMock()
    reader.get_hot_memories = AsyncMock(return_value=[])
    http = _app(monkeypatch, hot_reader=reader)
    with http:
        resp = _hot(http, org_id=OTHER_ORG)
    _assert_refused_without_leaking(resp, other_org=OTHER_ORG)
    reader.get_hot_memories.assert_not_awaited()


def test_hot_missing_org_header_uses_token_org(monkeypatch) -> None:
    reader = AsyncMock()
    reader.get_hot_memories = AsyncMock(return_value=[])
    http = _app(monkeypatch, hot_reader=reader)
    with http:
        resp = _hot(http, org_id=None)
    assert resp.status_code == 200
    query = reader.get_hot_memories.await_args.args[0]
    assert query.org_id == ORG


@pytest.mark.parametrize("org_id", [ORG, None])
def test_org_header_does_not_change_the_tenant(
    monkeypatch, org_id: object | None
) -> None:
    """Whatever the header says, the query is scoped to the token's org."""
    reader = AsyncMock()
    reader.get_hot_memories = AsyncMock(return_value=[])
    http = _app(monkeypatch, hot_reader=reader)
    with http:
        assert _hot(http, org_id=org_id).status_code == 200
    assert reader.get_hot_memories.await_args.args[0].org_id == ORG
