"""Bounded, tenant-scoped memory lineage traversal (milestone 5.B.1 / ADR-0094).

``ibex_core.memory_relationships`` records why a memory is no longer current,
and ``ibex_core.resolve_supersession_tip`` resolves one chain head, but nothing
walks the graph beyond a single hop. This module adds that walk.

The walk stays in SQL on purpose:

* the depth cap is a property of the query, so a caller cannot ask for an
  unbounded traversal and an application bug cannot loop;
* ``org_id`` is re-applied at every recursion level, not only at the base case,
  so a traversal can never cross a tenant boundary even if an edge row were
  written with the wrong ``org_id``;
* an agent-scoped caller's agent is applied to the root and to every joined
  node, so an edge cannot hand back another agent's memory id, status, or type;
* both directions are walked, because "what replaced this" and "what did this
  replace" are the same question asked from opposite ends.

Cycles terminate on the path array: a node already on the current path is not
re-entered. ``UNION ALL`` is deliberate -- two distinct paths to the same node
are legitimate -- and duplicates are collapsed per edge in the final projection.
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.org_context import set_service_org
from app.read.metrics import LINEAGE_LATENCY, LINEAGE_QUERIES

logger = logging.getLogger(__name__)

MAX_LINEAGE_DEPTH = 5
DEFAULT_LINEAGE_DEPTH = 3
MAX_LINEAGE_EDGES = 100

# The edge cap bounds the response, but the recursive walk itself has no row
# limit: path enumeration grows with fan-out, and a deliberately dense graph
# could hold a pooled connection far longer than a read may. A local statement
# timeout turns that into a fast 503 instead of a request that never returns.
# PostgreSQL reports it as a cancelled statement, which surfaces as SQLAlchemyError.
STATEMENT_TIMEOUT = "500ms"

# Root state and the supersession chain head in one round trip. The tip helper
# gets its own maximum depth, not the caller's: the tip is a property of the
# resource ("what is current"), so narrowing the edge walk must not silently
# turn it into "the immediate successor". The lateral join re-applies the
# tenant and agent boundary to the tip itself, so an agent-scoped caller can
# never receive another agent's memory id through this field.
_ROOT_SQL = """
SELECT m.id,
       m.status,
       m.tombstoned,
       COALESCE(tip.id, m.id) AS tip
FROM ibex_core.memories m
LEFT JOIN LATERAL (
    SELECT t.id
    FROM ibex_core.memories t
    WHERE t.id = ibex_core.resolve_supersession_tip(:org_id, m.id, :tip_depth)
      AND t.org_id = :org_id
      AND (CAST(:agent_id AS uuid) IS NULL OR t.agent_id = CAST(:agent_id AS uuid))
) AS tip ON TRUE
WHERE m.org_id = :org_id
  AND m.id = :memory_id
  AND (m.agent_id = CAST(:agent_id AS uuid) OR CAST(:agent_id AS uuid) IS NULL)
"""

# Both directions, depth capped in the recursive term, org and agent filters at
# every level, cycle break on the path array. `DISTINCT ON (edge_id)` keeps one
# row per edge at its shallowest depth so a diamond does not duplicate the output.
_LINEAGE_SQL = """
WITH RECURSIVE walk AS (
    SELECT
        m.id           AS node_id,
        0              AS depth,
        ARRAY[m.id]    AS path,
        NULL::uuid     AS edge_id,
        NULL::uuid     AS source_id,
        NULL::uuid     AS target_id,
        NULL::text     AS relationship_type,
        NULL::numeric  AS confidence,
        NULL::uuid     AS from_id
    FROM ibex_core.memories m
    WHERE m.org_id = :org_id
      AND m.id = :memory_id
      AND (CAST(:agent_id AS uuid) IS NULL OR m.agent_id = CAST(:agent_id AS uuid))

    UNION ALL

    SELECT
        CASE WHEN e.source_memory_id = w.node_id
             THEN e.target_memory_id
             ELSE e.source_memory_id END AS node_id,
        w.depth + 1 AS depth,
        w.path || (CASE WHEN e.source_memory_id = w.node_id
                        THEN e.target_memory_id
                        ELSE e.source_memory_id END) AS path,
        e.id           AS edge_id,
        e.source_memory_id,
        e.target_memory_id,
        e.relationship_type,
        e.confidence,
        w.node_id      AS from_id
    FROM walk w
    INNER JOIN ibex_core.memory_relationships e
        ON e.org_id = :org_id
       AND (e.source_memory_id = w.node_id OR e.target_memory_id = w.node_id)
    INNER JOIN ibex_core.memories next_m
        ON next_m.org_id = :org_id
       AND next_m.id = CASE WHEN e.source_memory_id = w.node_id
                            THEN e.target_memory_id
                            ELSE e.source_memory_id END
       AND (CAST(:agent_id AS uuid) IS NULL OR next_m.agent_id = CAST(:agent_id AS uuid))
    WHERE w.depth < :max_depth
      AND NOT (
        CASE WHEN e.source_memory_id = w.node_id
             THEN e.target_memory_id
             ELSE e.source_memory_id END = ANY (w.path)
      )
),
edges AS (
    SELECT DISTINCT ON (edge_id)
        edge_id,
        source_id,
        target_id,
        relationship_type,
        confidence,
        depth,
        from_id
    FROM walk
    WHERE edge_id IS NOT NULL
    ORDER BY edge_id, depth
)
SELECT
    e.edge_id,
    e.source_id,
    e.target_id,
    e.relationship_type,
    e.confidence,
    e.depth,
    e.from_id,
    other.id           AS other_id,
    other.status       AS other_status,
    other.tombstoned   AS other_tombstoned
FROM edges e
INNER JOIN ibex_core.memories other
    ON other.org_id = :org_id
   AND other.id = CASE WHEN e.from_id = e.source_id THEN e.target_id ELSE e.source_id END
   AND (CAST(:agent_id AS uuid) IS NULL OR other.agent_id = CAST(:agent_id AS uuid))
ORDER BY e.depth, e.relationship_type, e.edge_id
LIMIT :edge_limit
"""


@dataclass(frozen=True, slots=True)
class LineageQuery:
    """Inputs for ``MemoryLineageRepository.get_lineage``.

    ``agent_id`` is the token's agent binding when the caller is agent-scoped.
    Passing it turns another agent's memory into "not found" rather than a
    cross-agent metadata read; an org-scoped token leaves it ``None``.
    """

    org_id: UUID
    memory_id: UUID
    agent_id: UUID | None = None
    max_depth: int = DEFAULT_LINEAGE_DEPTH


@dataclass(frozen=True, slots=True)
class LineageRoot:
    """The memory the traversal started from, plus its chain head."""

    memory_id: UUID
    status: str
    tombstoned: bool
    supersession_tip: UUID


@dataclass(frozen=True, slots=True)
class LineageEndpoint:
    """The far end of an edge, with the state the caller needs to interpret it."""

    memory_id: UUID
    status: str
    tombstoned: bool


@dataclass(frozen=True, slots=True)
class LineageEdge:
    """One relationship edge, with the hop that reached it.

    ``from_memory_id`` is the node the walk arrived from, so a consumer can
    rebuild the chain without guessing direction from ``depth``.
    """

    source_memory_id: UUID
    target_memory_id: UUID
    relationship_type: str
    confidence: float
    depth: int
    from_memory_id: UUID
    other: LineageEndpoint


@dataclass(frozen=True, slots=True)
class LineageResult:
    """A bounded traversal result. ``truncated`` means more edges exist."""

    root: LineageRoot
    edges: tuple[LineageEdge, ...]
    truncated: bool
    max_depth: int


def validate_lineage_query(query: LineageQuery) -> None:
    if query.max_depth < 1 or query.max_depth > MAX_LINEAGE_DEPTH:
        msg = f"max_depth must be between 1 and {MAX_LINEAGE_DEPTH}"
        raise ValueError(msg)


class MemoryLineageRepository:
    """Tenant-scoped, depth-capped traversal of ``memory_relationships``."""

    def __init__(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        self._session_factory = session_factory

    async def get_lineage(self, query: LineageQuery) -> LineageResult | None:
        """Return the lineage, or ``None`` when the memory is not visible.

        "Not visible" covers both a different tenant and an agent-scoped caller
        asking about another agent's memory. Both must look identical to the
        caller: a distinguishable answer would leak existence.
        """
        validate_lineage_query(query)
        started = time.perf_counter()
        try:
            result = await self._load(query)
        except SQLAlchemyError:
            LINEAGE_QUERIES.labels(result="error").inc()
            raise
        finally:
            LINEAGE_LATENCY.observe(time.perf_counter() - started)
        if result is None:
            LINEAGE_QUERIES.labels(result="not_found").inc()
            return None
        LINEAGE_QUERIES.labels(result="found" if result.edges else "empty").inc()
        return result

    async def _load(self, query: LineageQuery) -> LineageResult | None:
        params = {
            "org_id": str(query.org_id),
            "memory_id": str(query.memory_id),
            "agent_id": str(query.agent_id) if query.agent_id is not None else None,
            "max_depth": query.max_depth,
            "tip_depth": MAX_LINEAGE_DEPTH,
            "edge_limit": MAX_LINEAGE_EDGES + 1,
        }
        async with self._session_factory() as session, session.begin():
            await set_service_org(session, query.org_id)
            await session.execute(
                text(  # nosemgrep: python.sqlalchemy.security.audit.avoid-sqlalchemy-text.avoid-sqlalchemy-text
                    "SELECT set_config('statement_timeout', :timeout, true)"
                ),
                {"timeout": STATEMENT_TIMEOUT},
            )
            root_row = (
                await session.execute(
                    text(  # nosemgrep: python.sqlalchemy.security.audit.avoid-sqlalchemy-text.avoid-sqlalchemy-text  # nosec B608
                        _ROOT_SQL
                    ),
                    params,
                )
            ).mappings().first()
            if root_row is None:
                return None
            edge_rows = (
                await session.execute(
                    text(  # nosemgrep: python.sqlalchemy.security.audit.avoid-sqlalchemy-text.avoid-sqlalchemy-text  # nosec B608
                        _LINEAGE_SQL
                    ),
                    params,
                )
            ).mappings().all()
        return LineageResult(
            root=LineageRoot(
                memory_id=UUID(str(root_row["id"])),
                status=str(root_row["status"]),
                tombstoned=bool(root_row["tombstoned"]),
                supersession_tip=UUID(str(root_row["tip"])),
            ),
            edges=_edges_from_rows(edge_rows),
            truncated=len(edge_rows) > MAX_LINEAGE_EDGES,
            max_depth=query.max_depth,
        )


def _edges_from_rows(rows: list[object]) -> tuple[LineageEdge, ...]:
    """Map traversal rows to edges, dropping the truncation probe row."""
    return tuple(
        LineageEdge(
            source_memory_id=UUID(str(row["source_id"])),
            target_memory_id=UUID(str(row["target_id"])),
            relationship_type=str(row["relationship_type"]),
            confidence=float(row["confidence"]),
            depth=int(row["depth"]),
            from_memory_id=UUID(str(row["from_id"])),
            other=LineageEndpoint(
                memory_id=UUID(str(row["other_id"])),
                status=str(row["other_status"]),
                tombstoned=bool(row["other_tombstoned"]),
            ),
        )
        for row in rows[:MAX_LINEAGE_EDGES]
    )
