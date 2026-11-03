"""Boundary and contract attacks on GET /v1/memories/{id}/lineage (ADR-0094).

Expected behaviour is taken from ADR-0094 and `engineering/API_DOCUMENTATION.md`,
not from the implementation:

* `edges` is capped at 100 with `truncated=true` **only when more exist**;
* `supersession_tip` is "the current tip of the supersession chain";
* a memory outside an agent-scoped token's agent is not visible;
* every edge is reported once, at its shallowest depth;
* all six relationship types are walked.
"""

from __future__ import annotations

from uuid import UUID

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.read.lineage import MAX_LINEAGE_EDGES, LineageQuery
from tests.integration.lineage_support import LineageGraph

pytestmark = pytest.mark.integration

ALL_TYPES = (
    "supersedes",
    "contradicts",
    "specializes",
    "generalizes",
    "merged_from",
    "derived_from",
)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("count", "expected_truncated"),
    [
        (MAX_LINEAGE_EDGES, False),
        (MAX_LINEAGE_EDGES + 1, True),
    ],
)
async def test_edge_cap_boundary_is_exact(
    session_factory: async_sessionmaker[AsyncSession],
    count: int,
    expected_truncated: bool,
) -> None:
    """The cap must not flap: 100 edges fit, 101 report truncation."""
    graph, root = await LineageGraph.seed(session_factory, "edge cap root")
    await graph.fan_out(root, count)

    result = await graph.repo().get_lineage(
        LineageQuery(org_id=graph.org_id, memory_id=root, max_depth=1)
    )

    assert result is not None
    assert len(result.edges) == MAX_LINEAGE_EDGES
    assert result.truncated is expected_truncated


@pytest.mark.asyncio
async def test_supersession_tip_is_the_chain_head_at_every_depth(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    """API docs: `supersession_tip` is "the current tip of the supersession chain".

    It is documented as a property of the resource, so it must not silently
    become the immediate successor just because the caller also bounded the edge
    walk with `max_depth`.
    """
    graph, root = await LineageGraph.seed(session_factory, "tip-depth root")
    successor = await graph.memory("tip-depth 1", status="superseded")
    head = await graph.memory("tip-depth 2")
    await graph.link(successor, root)
    await graph.link(head, successor)

    shallow = await graph.repo().get_lineage(
        LineageQuery(org_id=graph.org_id, memory_id=root, max_depth=1)
    )
    deep = await graph.repo().get_lineage(
        LineageQuery(org_id=graph.org_id, memory_id=root, max_depth=3)
    )

    assert shallow is not None and deep is not None
    assert deep.root.supersession_tip == head
    assert shallow.root.supersession_tip == head, (
        "supersession_tip is documented as the chain head, but max_depth=1 "
        f"returned {shallow.root.supersession_tip} instead of {head}"
    )


@pytest.mark.asyncio
async def test_agent_scoped_traversal_does_not_reveal_a_peer_agents_memory(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    """An agent-scoped token may not read another agent's memory by id.

    Nothing in the read path lets that token see the peer memory, so the
    traversal should not hand back its id, status, and relationship type either.
    """
    graph, root = await LineageGraph.seed(session_factory, "agent scope root")
    peer_agent = await graph.second_agent()
    peer_memory = await graph.memory("peer agent memory", agent_id=peer_agent)
    await graph.link(root, peer_memory)

    scoped = await graph.repo().get_lineage(
        LineageQuery(
            org_id=graph.org_id,
            memory_id=root,
            agent_id=graph.agent_id,
            max_depth=3,
        )
    )
    org_wide = await graph.repo().get_lineage(
        LineageQuery(org_id=graph.org_id, memory_id=root, agent_id=None, max_depth=3)
    )

    assert scoped is not None
    assert scoped.root.memory_id == root
    assert [edge.other.memory_id for edge in scoped.edges] == [], (
        "agent-scoped lineage exposed a peer agent's memory: "
        f"{[str(edge.other.memory_id) for edge in scoped.edges]}"
    )
    assert org_wide is not None
    assert [edge.other.memory_id for edge in org_wide.edges] == [peer_memory]


@pytest.mark.asyncio
async def test_diamond_reports_each_edge_once_at_its_shallowest_depth(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    graph, root = await LineageGraph.seed(session_factory, "diamond root")
    left = await graph.memory("diamond left")
    right = await graph.memory("diamond right")
    bottom = await graph.memory("diamond bottom")
    await graph.link(root, left, "derived_from")
    await graph.link(root, right, "derived_from")
    await graph.link(left, bottom, "derived_from")
    await graph.link(right, bottom, "derived_from")

    result = await graph.repo().get_lineage(
        LineageQuery(org_id=graph.org_id, memory_id=root, max_depth=5)
    )

    assert result is not None
    pairs = [(edge.source_memory_id, edge.target_memory_id) for edge in result.edges]
    assert len(pairs) == 4
    assert len(set(pairs)) == 4
    depths = {
        (edge.source_memory_id, edge.target_memory_id): edge.depth
        for edge in result.edges
    }
    assert depths[(root, left)] == 1
    assert depths[(root, right)] == 1
    assert depths[(left, bottom)] == 2
    assert depths[(right, bottom)] == 2


@pytest.mark.asyncio
async def test_all_six_relationship_types_are_walked(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    graph, root = await LineageGraph.seed(session_factory, "six types root")
    neighbours: dict[str, UUID] = {}
    for relationship_type in ALL_TYPES:
        neighbour = await graph.memory(f"neighbour {relationship_type}")
        neighbours[relationship_type] = neighbour
        await graph.link(neighbour, root, relationship_type)

    result = await graph.repo().get_lineage(
        LineageQuery(org_id=graph.org_id, memory_id=root, max_depth=1)
    )

    assert result is not None
    assert {
        edge.relationship_type: edge.other.memory_id for edge in result.edges
    } == neighbours
    assert all(edge.depth == 1 for edge in result.edges)
