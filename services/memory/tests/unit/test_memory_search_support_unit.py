"""Unit tests for memory search HTTP helpers."""

from __future__ import annotations

from contextlib import nullcontext
from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest
from fastapi import HTTPException
from sqlalchemy.exc import DBAPIError

from app.auth.client import ValidateResult
from app.clients.embedding import EmbeddingClientError
from app.exceptions import EmbeddingServiceError
from app.read.models import FindSimilarQuery, MemorySearchResult
from app.routers.memory_search_support import (
    SearchMemoriesExecution,
    embed_query_text,
    ensure_search_agent_authorized,
    find_similar_query_from_execution,
    http_error_for_search,
    log_search_database_failure,
    resolve_search_agent_id,
    run_memory_search,
    search_response_from_results,
)
from app.schemas.search import SearchMemoriesRequest


def _result() -> MemorySearchResult:
    now = datetime.now(UTC)
    return MemorySearchResult(
        id=uuid4(),
        org_id=uuid4(),
        agent_id=uuid4(),
        content="content",
        category="factual",
        confidence=0.9,
        status="active",
        similarity=0.95,
        source="vector",
        created_at=now,
        updated_at=now,
    )


def test_search_response_from_results_assigns_rank() -> None:
    item = _result()
    response = search_response_from_results([item])
    assert response.data.results[0].rank == 1
    assert response.data.results[0].similarity == pytest.approx(0.95)
    assert response.data.results[0].source == "vector"


def test_http_error_for_search_embedding() -> None:
    exc = http_error_for_search(EmbeddingServiceError("down"))
    assert exc.status_code == 503
    assert exc.detail["code"] == "EMBEDDING_FAILED"


def test_http_error_for_search_validation() -> None:
    exc = http_error_for_search(ValueError("bad limit"))
    assert exc.status_code == 400


def test_http_error_for_search_database() -> None:
    exc = http_error_for_search(DBAPIError("stmt", {}, Exception("db down")))
    assert exc.status_code == 503
    assert exc.detail["code"] == "DATABASE_UNAVAILABLE"


def test_http_error_for_search_reraises_unknown() -> None:
    with pytest.raises(RuntimeError):
        http_error_for_search(RuntimeError("boom"))


def test_log_search_database_failure_logs_exc_type() -> None:
    org_id = uuid4()
    with patch("app.routers.memory_search_support.logger") as mock_logger:
        log_search_database_failure(DBAPIError("stmt", {}, Exception("db down")), org_id=org_id)
    mock_logger.exception.assert_called_once()
    call_args = mock_logger.exception.call_args
    assert "exc_type=%s" in call_args.args[0]
    assert call_args.args[1] == "DBAPIError"
    assert call_args.args[2] == str(org_id)


def test_find_similar_query_from_execution() -> None:
    org_id = uuid4()
    agent_id = uuid4()
    request = SearchMemoriesRequest(agent_id=agent_id, query="q", limit=3, min_similarity=0.5)
    execution = SearchMemoriesExecution.from_request(
        org_id=org_id,
        agent_id=agent_id,
        request=request,
        query_embedding=[0.0] * 1024,
    )
    query = find_similar_query_from_execution(execution)
    assert query == FindSimilarQuery(
        org_id=org_id,
        agent_id=agent_id,
        query_embedding=[0.0] * 1024,
        query_text="q",
        limit=3,
        min_similarity=0.5,
        min_confidence=0.0,
    )


def test_resolve_search_agent_id_allows_org_scoped_token() -> None:
    agent_id = uuid4()
    token = ValidateResult(org_id=uuid4(), permissions=0)
    assert resolve_search_agent_id(token, agent_id) is agent_id


def test_resolve_search_agent_id_rejects_mismatch() -> None:
    token = ValidateResult(org_id=uuid4(), permissions=0, agent_id=uuid4())
    with pytest.raises(HTTPException) as exc:
        resolve_search_agent_id(token, uuid4())
    assert exc.value.status_code == 403
    assert exc.value.detail["code"] == "AGENT_NOT_AUTHORIZED"


def _mock_session_factory(scalar: object | None) -> MagicMock:
    session = AsyncMock()
    session.execute = AsyncMock(return_value=MagicMock(scalar=MagicMock(return_value=scalar)))
    factory = MagicMock()
    factory.return_value.__aenter__ = AsyncMock(return_value=session)
    factory.return_value.__aexit__ = AsyncMock(return_value=None)
    return factory


async def _assert_ensure_search_agent_authorized(
    *,
    scalar: object | None,
    expect_forbidden: bool,
) -> None:
    factory = _mock_session_factory(scalar)
    raises = pytest.raises(HTTPException) if expect_forbidden else nullcontext()
    with (
        patch(
            "app.routers.memory_search_support.set_service_org",
            new_callable=AsyncMock,
        ),
        raises as exc_info,
    ):
        await ensure_search_agent_authorized(
            factory,
            org_id=uuid4(),
            agent_id=uuid4(),
        )
    if expect_forbidden:
        assert exc_info.value.status_code == 403
        assert exc_info.value.detail["code"] == "AGENT_NOT_AUTHORIZED"


@pytest.mark.asyncio
async def test_ensure_search_agent_authorized_rejects_missing_agent() -> None:
    await _assert_ensure_search_agent_authorized(scalar=None, expect_forbidden=True)


@pytest.mark.asyncio
async def test_ensure_search_agent_authorized_allows_member_agent() -> None:
    await _assert_ensure_search_agent_authorized(scalar=1, expect_forbidden=False)


@pytest.mark.asyncio
async def test_embed_query_text_success() -> None:
    client = MagicMock()
    client.embed = AsyncMock(
        return_value=MagicMock(vectors=[[0.1] * 1024], model_id="m", dimensions=1024)
    )
    vec = await embed_query_text(client, org_id=uuid4(), query="hello")
    assert len(vec) == 1024


@pytest.mark.asyncio
async def test_embed_query_text_maps_client_error() -> None:
    client = MagicMock()
    client.embed = AsyncMock(side_effect=EmbeddingClientError("down"))
    with pytest.raises(EmbeddingServiceError):
        await embed_query_text(client, org_id=uuid4(), query="hello")


@pytest.mark.asyncio
async def test_run_memory_search_delegates() -> None:
    repo = MagicMock()
    repo.find_similar = AsyncMock(return_value=[])
    org_id = uuid4()
    agent_id = uuid4()
    request = SearchMemoriesRequest(agent_id=agent_id, query="q", limit=3, min_similarity=0.5)
    execution = SearchMemoriesExecution.from_request(
        org_id=org_id,
        agent_id=agent_id,
        request=request,
        query_embedding=[0.0] * 1024,
    )
    await run_memory_search(repo, execution)
    repo.find_similar.assert_awaited_once_with(
        find_similar_query_from_execution(execution)
    )
