"""GIN full-text search for memory read fallback (milestone 3.D.1)."""

from __future__ import annotations

from dataclasses import dataclass, field
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.org_context import set_service_org

# Shared with EXPLAIN plan tests — keep in sync with full_text_search().
FTS_SQL = """
SELECT id::text AS memory_id,
       ts_rank_cd(
           search_vector,
           plainto_tsquery('english', :query_text)
       )::float8 AS rank
FROM ibex_core.memories
WHERE org_id = :org_id
  AND agent_id = :agent_id
  AND status = 'active'
  AND deleted_at IS NULL
  AND confidence >= :min_confidence
  AND search_vector @@ plainto_tsquery('english', :query_text)
ORDER BY rank DESC
LIMIT :limit
"""


@dataclass(frozen=True, slots=True)
class FullTextHit:
    memory_id: UUID
    rank: float


@dataclass(frozen=True, slots=True)
class FullTextSearchQuery:
    org_id: UUID
    agent_id: UUID
    query_text: str
    limit: int
    min_confidence: float
    exclude_ids: frozenset[UUID] = field(default_factory=frozenset)


def is_searchable_query(query_text: str) -> bool:
    """Return False for blank or whitespace-only queries (skip FTS, no error)."""
    return bool(query_text.strip())


async def full_text_search(
    session_factory: async_sessionmaker[AsyncSession],
    query: FullTextSearchQuery,
) -> list[FullTextHit]:
    """Org/agent-scoped GIN search; excludes IDs already returned by vector path."""
    if query.limit < 1 or not is_searchable_query(query.query_text):
        return []

    async with session_factory() as session, session.begin():
        await set_service_org(session, query.org_id)
        result = await session.execute(
            text(  # nosemgrep: python.sqlalchemy.security.audit.avoid-sqlalchemy-text.avoid-sqlalchemy-text
                FTS_SQL
            ),
            {
                "org_id": str(query.org_id),
                "agent_id": str(query.agent_id),
                "query_text": query.query_text.strip(),
                "min_confidence": query.min_confidence,
                "limit": query.limit,
            },
        )
        rows = result.mappings().all()

    hits: list[FullTextHit] = []
    for row in rows:
        memory_id = UUID(str(row["memory_id"]))
        if memory_id in query.exclude_ids:
            continue
        hits.append(FullTextHit(memory_id=memory_id, rank=float(row["rank"])))
        if len(hits) >= query.limit:
            break
    return hits
