"""EXPLAIN helpers for memory index plan gates (outside services/ Semgrep scan path).

Reachability / safety (milestone 3.D.1, Semgrep relocation):
- Imported only from integration test shims (`services/memory/tests/integration/plan_assert.py`)
  and `test_find_similar_plans.py` — never from `app/` or any production request path.
- `text()` + interpolated `SEARCH_SQL` is acceptable here because `org_id`, `agent_id`, and
  query vectors are supplied by test fixtures with bounded, controlled literals (same rigor as
  a justified `nosemgrep` annotation).
- GIN runtime verification uses a test-only probe transaction that drops competing
  partial btree indexes (rolled back with the session), disables RLS, and applies planner
  hints (`explain_gin_probe_plan` + `assert_gin_index_used`) in `test_gin_index_used_at_runtime`;
  production `full_text_search()` correctness is asserted separately in the same test.
"""

from __future__ import annotations

from dataclasses import dataclass
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.vectorstore.pgvector_store import SEARCH_SQL

# Probe keeps partial-index predicates (status/deleted_at) so idx_memories_search_vector
# is eligible; org/agent are omitted so production btree paths are not required.
GIN_PROBE_SQL = """
SELECT id::text AS memory_id
FROM ibex_core.memories
WHERE status = 'active'
  AND deleted_at IS NULL
  AND search_vector @@ plainto_tsquery('english', :query_text)
LIMIT 1
"""

# Partial btree indexes sharing the probe's status/deleted_at predicate; dropped inside the
# probe transaction so EXPLAIN must use idx_memories_search_vector (restored on rollback).
_DROP_GIN_COMPETING_INDEXES_SQL = (
    "DROP INDEX IF EXISTS ibex_core.idx_memories_agent_active",
    "DROP INDEX IF EXISTS ibex_core.idx_memories_org_agent_content_hash_active",
    "DROP INDEX IF EXISTS ibex_core.idx_memories_validity",
)

_EXPLAIN_PREFIX = "EXPLAIN (ANALYZE, BUFFERS, FORMAT JSON) "


@dataclass(frozen=True, slots=True)
class GinExplainParams:
    query_text: str


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
    explain_sql = _EXPLAIN_PREFIX + SEARCH_SQL
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


async def _hide_gin_competing_indexes(session: AsyncSession) -> None:
    """Drop btree indexes that compete with the partial GIN index for the probe shape."""
    for stmt in _DROP_GIN_COMPETING_INDEXES_SQL:
        await session.execute(
            text(stmt),  # nosemgrep: python.sqlalchemy.security.audit.avoid-sqlalchemy-text.avoid-sqlalchemy-text
        )


async def prepare_gin_probe_session(session: AsyncSession) -> None:
    """Test-only settings so the FTS probe must use idx_memories_search_vector.

    Competing partial btree indexes (same status/deleted_at predicate) otherwise win with
    heap filters on @@; drop them for the probe transaction only, disable RLS, and force
    seqscan off so EXPLAIN shows GIN bitmap/index access.
    """
    await _hide_gin_competing_indexes(session)
    await session.execute(
        text(  # nosemgrep: python.sqlalchemy.security.audit.avoid-sqlalchemy-text.avoid-sqlalchemy-text
            "SET LOCAL row_security = off"
        )
    )
    await _apply_gin_probe_planner_hints(session)


async def explain_gin_probe_plan(
    session: AsyncSession,
    params: GinExplainParams,
) -> object:
    """EXPLAIN FTS probe with test-only settings that force GIN index access.

    Competing-index drops run in a nested transaction that is always rolled back so
    DDL never commits when the integration test session ends.
    """
    nested = await session.begin_nested()
    try:
        await prepare_gin_probe_session(session)
        explain_sql = _EXPLAIN_PREFIX + GIN_PROBE_SQL
        result = await session.execute(
            text(explain_sql),  # nosemgrep: python.sqlalchemy.security.audit.avoid-sqlalchemy-text.avoid-sqlalchemy-text
            {"query_text": params.query_text.strip()},
        )
        return result.scalar_one()
    finally:
        await nested.rollback()


async def _apply_gin_probe_planner_hints(session: AsyncSession) -> None:
    for stmt in (
        "SET LOCAL enable_seqscan = OFF",
        "SET LOCAL max_parallel_workers_per_gather = 0",
    ):
        await session.execute(
            text(stmt),  # nosemgrep: python.sqlalchemy.security.audit.avoid-sqlalchemy-text.avoid-sqlalchemy-text
        )


async def run_gin_probe(session: AsyncSession, params: GinExplainParams) -> None:
    """Execute the FTS probe (for pg_stat idx_scan gates)."""
    nested = await session.begin_nested()
    try:
        await prepare_gin_probe_session(session)
        await session.execute(
            text(GIN_PROBE_SQL),  # nosemgrep: python.sqlalchemy.security.audit.avoid-sqlalchemy-text.avoid-sqlalchemy-text
            {"query_text": params.query_text.strip()},
        )
    finally:
        await nested.rollback()
