"""HTTP helpers for POST /v1/memories/search."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from uuid import UUID

from fastapi import HTTPException
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.auth.client import ValidateResult
from app.clients.embedding import EmbeddingClient, EmbeddingClientError
from app.exceptions import EmbeddingServiceError, MemoryDatabaseError
from app.org_context import set_service_org
from app.read.models import FindSimilarQuery, MemorySearchResult
from app.read.repository import MemoryReadRepository
from app.schemas.search import (
    SearchMemoriesData,
    SearchMemoriesRequest,
    SearchMemoriesResponse,
    SearchMemoryHit,
    SearchResultItem,
)

logger = logging.getLogger(__name__)


def log_search_database_failure(exc: BaseException, *, org_id: UUID | None = None) -> None:
    """Log database failures with type and stack trace; never log query text or memory content."""
    logger.exception(
        "memory search database failure exc_type=%s org_id=%s",
        type(exc).__name__,
        str(org_id) if org_id is not None else None,
    )


def http_error_for_search(exc: BaseException) -> HTTPException:
    if isinstance(exc, EmbeddingServiceError):
        return HTTPException(
            status_code=503,
            detail={"code": exc.code, "message": exc.message},
        )
    if isinstance(exc, ValueError):
        return HTTPException(
            status_code=400,
            detail={"code": "VALIDATION_ERROR", "message": str(exc)},
        )
    if isinstance(exc, SQLAlchemyError):
        return HTTPException(
            status_code=MemoryDatabaseError.http_status,
            detail={
                "code": MemoryDatabaseError.code,
                "message": "Database unavailable",
            },
        )
    raise exc


def resolve_search_agent_id(token: ValidateResult, requested_agent_id: UUID) -> UUID:
    """Reject agent-scoped tokens that target a different agent."""
    if token.agent_id is not None and token.agent_id != requested_agent_id:
        raise HTTPException(
            status_code=403,
            detail={
                "code": "AGENT_NOT_AUTHORIZED",
                "message": "Token is not authorized for the requested agent",
            },
        )
    return requested_agent_id


_AGENT_ORG_CHECK_SQL = """
SELECT 1
FROM ibex_core.agents
WHERE id = :agent_id
  AND org_id = :org_id
LIMIT 1
"""


async def ensure_search_agent_authorized(
    session_factory: async_sessionmaker[AsyncSession],
    *,
    org_id: UUID,
    agent_id: UUID,
) -> None:
    """Reject search when the requested agent does not belong to the token org."""
    async with session_factory() as session:
        await set_service_org(session, org_id)
        found = (
            await session.execute(
                text(
                    _AGENT_ORG_CHECK_SQL
                ),  # nosemgrep: python.sqlalchemy.security.audit.avoid-sqlalchemy-text.avoid-sqlalchemy-text
                {"agent_id": str(agent_id), "org_id": str(org_id)},
            )
        ).scalar()
    if found is None:
        raise HTTPException(
            status_code=403,
            detail={
                "code": "AGENT_NOT_AUTHORIZED",
                "message": "Agent does not belong to the authenticated organization",
            },
        )


async def embed_query_text(
    client: EmbeddingClient,
    *,
    org_id: UUID,
    query: str,
) -> list[float]:
    try:
        result = await client.embed([query], org_id=org_id)
    except EmbeddingClientError as exc:
        raise EmbeddingServiceError(exc.message) from exc
    return list(result.vectors[0])


def search_response_from_results(results: list[MemorySearchResult]) -> SearchMemoriesResponse:
    items = [
        SearchResultItem(
            memory=SearchMemoryHit(
                id=item.id,
                agent_id=item.agent_id,
                org_id=item.org_id,
                content=item.content,
                category=item.category,
                confidence=item.confidence,
                status=item.status,
                created_at=item.created_at,
                updated_at=item.updated_at,
            ),
            similarity=item.similarity,
            rank=index,
            source=item.source,
        )
        for index, item in enumerate(results, start=1)
    ]
    return SearchMemoriesResponse(data=SearchMemoriesData(results=items))


@dataclass(frozen=True, slots=True)
class SearchMemoriesExecution:
    """Authenticated search inputs for the read repository."""

    org_id: UUID
    agent_id: UUID
    request: SearchMemoriesRequest
    query_embedding: list[float]

    @classmethod
    def from_request(
        cls,
        *,
        org_id: UUID,
        agent_id: UUID,
        request: SearchMemoriesRequest,
        query_embedding: list[float],
    ) -> SearchMemoriesExecution:
        return cls(
            org_id=org_id,
            agent_id=agent_id,
            request=request,
            query_embedding=query_embedding,
        )


async def run_memory_search(
    repo: MemoryReadRepository,
    execution: SearchMemoriesExecution,
) -> list[MemorySearchResult]:
    return await repo.find_similar(find_similar_query_from_execution(execution))


def find_similar_query_from_execution(
    execution: SearchMemoriesExecution,
) -> FindSimilarQuery:
    return FindSimilarQuery(
        org_id=execution.org_id,
        agent_id=execution.agent_id,
        query_embedding=execution.query_embedding,
        query_text=execution.request.query,
        limit=execution.request.limit,
        min_similarity=execution.request.min_similarity,
        min_confidence=execution.request.min_confidence,
    )
