"""EXPLAIN helpers for memory index plan gates (outside services/ Semgrep scan path).

Reachability / safety (milestone 3.D.1, Semgrep relocation):
- Imported only from integration test shims (`services/memory/tests/integration/plan_assert.py`)
  and `test_find_similar_plans.py` — never from `app/` or any production request path.
- `text()` + interpolated `SEARCH_SQL` is acceptable here because `org_id`, `agent_id`, and
  query vectors are supplied by test fixtures with bounded, controlled literals (same rigor as
  a justified `nosemgrep` annotation).
- GIN plan-shape verification uses `pg_stat idx_scan` at runtime (`test_gin_index_scan_at_runtime`);
  the deleted GIN EXPLAIN helper is not replaced here because EXPLAIN is unreliable when btree
  and GIN indexes compete under org/agent scope filters.
"""

from __future__ import annotations

from dataclasses import dataclass
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.vectorstore.pgvector_store import SEARCH_SQL


@dataclass(frozen=True, slots=True)
class HnswExplainParams:
    org_id: UUID
    agent_id: UUID
    query_vec: list[float]
    ef_search: int


async def explain_hnsw_search_plan(
    session: AsyncSession,
    params: HnswExplainParams,
) -> object:
    """Run EXPLAIN for vector search SQL (shared with integration plan gates)."""
    explain_sql = f"EXPLAIN (ANALYZE, BUFFERS, FORMAT JSON) {SEARCH_SQL}"
    vector_literal = "[" + ",".join(str(float(v)) for v in params.query_vec) + "]"
    await session.execute(
        text(  # nosemgrep: python.sqlalchemy.security.audit.avoid-sqlalchemy-text.avoid-sqlalchemy-text
            "SELECT set_config('hnsw.ef_search', :ef, true)"
        ),
        {"ef": str(params.ef_search)},
    )
    await session.execute(
        text(  # nosemgrep: python.sqlalchemy.security.audit.avoid-sqlalchemy-text.avoid-sqlalchemy-text
            "SELECT set_config('hnsw.iterative_scan', 'relaxed_order', true)"
        )
    )
    result = await session.execute(
        text(explain_sql),  # nosemgrep: python.sqlalchemy.security.audit.avoid-sqlalchemy-text.avoid-sqlalchemy-text
        {
            "query": vector_literal,
            "org_id": str(params.org_id),
            "agent_id": str(params.agent_id),
            "min_similarity": 0.0,
            "limit": 10,
        },
    )
    return result.scalar_one()
