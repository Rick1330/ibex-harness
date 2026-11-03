"""Graph seeding for the lineage integration tests (milestone 5.B.1)."""

from __future__ import annotations

from uuid import UUID, uuid4

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.read.lineage import MemoryLineageRepository
from tests.integration.conftest import seed_org_agent_memory, with_service_org


class LineageGraph:
    """One seeded org/agent plus the helpers its traversal tests need.

    Holding the tenant makes every call site a two-argument operation, which
    keeps the tests about the graph shape rather than about seed plumbing.
    """

    def __init__(
        self,
        factory: async_sessionmaker[AsyncSession],
        org_id: UUID,
        agent_id: UUID,
    ) -> None:
        self._factory = factory
        self._org_id = org_id
        self._agent_id = agent_id

    @classmethod
    async def seed(
        cls,
        factory: async_sessionmaker[AsyncSession],
        content: str,
    ) -> tuple[LineageGraph, UUID]:
        org_id, agent_id, root = await seed_org_agent_memory(factory, content=content)
        return cls(factory, org_id, agent_id), root

    @property
    def org_id(self) -> UUID:
        return self._org_id

    @property
    def agent_id(self) -> UUID:
        return self._agent_id

    def repo(self) -> MemoryLineageRepository:
        return MemoryLineageRepository(self._factory)

    async def memory(
        self,
        content: str,
        status: str = "active",
        agent_id: UUID | None = None,
    ) -> UUID:
        """Insert a memory; ``agent_id`` defaults to the seeded agent."""
        memory_id = uuid4()
        async with self._factory() as session, session.begin():
            await with_service_org(session, self._org_id)
            await session.execute(
                text(  # nosemgrep: python.sqlalchemy.security.audit.avoid-sqlalchemy-text.avoid-sqlalchemy-text
                    """
                    INSERT INTO ibex_core.memories (
                        id, org_id, agent_id, content, content_hash, content_tokens, status
                    ) VALUES (
                        :id, :org_id, :agent_id, :content, :hash, 3, :status
                    )
                    """
                ),
                {
                    "id": str(memory_id),
                    "org_id": str(self._org_id),
                    "agent_id": str(agent_id or self._agent_id),
                    "content": content,
                    "hash": f"{content}-{memory_id}",
                    "status": status,
                },
            )
        return memory_id

    async def link(
        self,
        source: UUID,
        target: UUID,
        relationship_type: str = "supersedes",
    ) -> None:
        async with self._factory() as session, session.begin():
            await with_service_org(session, self._org_id)
            await session.execute(
                text(  # nosemgrep: python.sqlalchemy.security.audit.avoid-sqlalchemy-text.avoid-sqlalchemy-text
                    """
                    INSERT INTO ibex_core.memory_relationships (
                        org_id, source_memory_id, target_memory_id,
                        relationship_type, confidence
                    ) VALUES (
                        :org_id, :source_id, :target_id, :relationship_type, 0.9
                    )
                    """
                ),
                {
                    "org_id": str(self._org_id),
                    "source_id": str(source),
                    "target_id": str(target),
                    "relationship_type": relationship_type,
                },
            )

    async def fan_out(
        self,
        root: UUID,
        count: int,
        *,
        relationship_type: str = "specializes",
    ) -> None:
        """Attach ``count`` fresh memories to ``root`` in one statement."""
        async with self._factory() as session, session.begin():
            await with_service_org(session, self._org_id)
            await session.execute(
                text(  # nosemgrep: python.sqlalchemy.security.audit.avoid-sqlalchemy-text.avoid-sqlalchemy-text
                    """
                    WITH created AS (
                        INSERT INTO ibex_core.memories (
                            id, org_id, agent_id, content, content_hash, content_tokens
                        )
                        SELECT gen_random_uuid(), CAST(:org_id AS uuid), CAST(:agent_id AS uuid),
                               'fan ' || series,
                               'fan-hash-' || :root_hash || '-' || series, 3
                        FROM generate_series(1, :count) AS series
                        RETURNING id
                    )
                    INSERT INTO ibex_core.memory_relationships (
                        org_id, source_memory_id, target_memory_id,
                        relationship_type, confidence
                    )
                    SELECT CAST(:org_id AS uuid), CAST(:root AS uuid), id,
                           :relationship_type, 0.9
                    FROM created
                    """
                ),
                {
                    "org_id": str(self._org_id),
                    "agent_id": str(self._agent_id),
                    "root": str(root),
                    "root_hash": str(root),
                    "count": count,
                    "relationship_type": relationship_type,
                },
            )

    async def second_agent(self) -> UUID:
        """A peer agent in the same organization, for cross-agent scope tests."""
        agent_id = uuid4()
        async with self._factory() as session, session.begin():
            await with_service_org(session, self._org_id)
            await session.execute(
                text(  # nosemgrep: python.sqlalchemy.security.audit.avoid-sqlalchemy-text.avoid-sqlalchemy-text
                    """
                    INSERT INTO ibex_core.agents (id, org_id, created_by, name, slug)
                    SELECT :id, :org_id, created_by, 'Peer agent', :slug
                    FROM ibex_core.agents
                    WHERE id = :template
                    """
                ),
                {
                    "id": str(agent_id),
                    "org_id": str(self._org_id),
                    "template": str(self._agent_id),
                    "slug": f"peer-{agent_id.hex[:8]}",
                },
            )
        return agent_id
