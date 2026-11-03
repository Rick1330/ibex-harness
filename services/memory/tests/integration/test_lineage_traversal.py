"""Postgres integration coverage for bounded lineage traversal (milestone 5.B.1).

The traversal is asserted against a real database because the properties that
matter -- the depth cap, the cycle break, and the tenant predicate at every
recursion level -- are properties of the SQL, not of the Python around it.
"""

from __future__ import annotations

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.read.lineage import LineageQuery
from tests.integration.lineage_support import LineageGraph

pytestmark = pytest.mark.integration


@pytest.mark.asyncio
async def test_traversal_walks_both_directions(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    graph, root = await LineageGraph.seed(session_factory, "root memory")
    newer = await graph.memory("newer")
    older = await graph.memory("older", status="superseded")
    rival = await graph.memory("rival")
    await graph.link(newer, root)
    await graph.link(root, older)
    await graph.link(rival, root, "contradicts")

    result = await graph.repo().get_lineage(
        LineageQuery(org_id=graph.org_id, memory_id=root, max_depth=1)
    )

    assert result is not None
    assert len(result.edges) == 3
    assert all(edge.depth == 1 for edge in result.edges)
    assert all(edge.from_memory_id == root for edge in result.edges)
    assert {edge.relationship_type for edge in result.edges} == {
        "supersedes",
        "contradicts",
    }
    by_other = {edge.other.memory_id: edge for edge in result.edges}
    assert by_other[older].other.status == "superseded"
    assert by_other[newer].other.status == "active"


@pytest.mark.asyncio
async def test_depth_cap_is_enforced_by_the_query(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    graph, root = await LineageGraph.seed(session_factory, "chain root")
    chain = [root]
    for index in range(1, 7):
        memory_id = await graph.memory(f"chain {index}")
        await graph.link(memory_id, chain[-1])
        chain.append(memory_id)

    shallow = await graph.repo().get_lineage(
        LineageQuery(org_id=graph.org_id, memory_id=root, max_depth=3)
    )
    deep = await graph.repo().get_lineage(
        LineageQuery(org_id=graph.org_id, memory_id=root, max_depth=5)
    )

    assert shallow is not None
    assert {edge.depth for edge in shallow.edges} <= {1, 2, 3}
    assert max(edge.depth for edge in shallow.edges) == 3
    assert deep is not None
    assert max(edge.depth for edge in deep.edges) == 5
    reached = {edge.other.memory_id for edge in deep.edges}
    assert chain[5] in reached
    assert chain[6] not in reached


@pytest.mark.asyncio
async def test_cycle_terminates_without_repeating_edges(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    graph, first = await LineageGraph.seed(session_factory, "cycle a")
    second = await graph.memory("cycle b")
    third = await graph.memory("cycle c")
    await graph.link(second, first)
    await graph.link(third, second)
    await graph.link(first, third)

    result = await graph.repo().get_lineage(
        LineageQuery(org_id=graph.org_id, memory_id=first, max_depth=5)
    )

    assert result is not None
    assert len(result.edges) == 3
    assert len({(e.source_memory_id, e.target_memory_id) for e in result.edges}) == 3


@pytest.mark.asyncio
async def test_cross_tenant_edges_are_never_traversed(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    graph_a, root_a = await LineageGraph.seed(session_factory, "org a root")
    peer_a = await graph_a.memory("org a peer")
    await graph_a.link(peer_a, root_a)

    graph_b, root_b = await LineageGraph.seed(session_factory, "org b root")
    peer_b = await graph_b.memory("org b peer")
    await graph_b.link(peer_b, root_b)

    foreign = await graph_a.repo().get_lineage(
        LineageQuery(org_id=graph_a.org_id, memory_id=root_b, max_depth=5)
    )
    local = await graph_a.repo().get_lineage(
        LineageQuery(org_id=graph_a.org_id, memory_id=root_a, max_depth=5)
    )

    assert foreign is None
    assert local is not None
    assert {edge.other.memory_id for edge in local.edges} == {peer_a}


@pytest.mark.asyncio
async def test_agent_scope_hides_another_agents_memory(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    graph, _root = await LineageGraph.seed(session_factory, "agent scoped root")
    other_agent = await graph.second_agent()
    foreign_memory = await graph.memory("other agent memory", agent_id=other_agent)

    scoped = await graph.repo().get_lineage(
        LineageQuery(
            org_id=graph.org_id,
            memory_id=foreign_memory,
            agent_id=graph.agent_id,
            max_depth=3,
        )
    )
    org_wide = await graph.repo().get_lineage(
        LineageQuery(
            org_id=graph.org_id,
            memory_id=foreign_memory,
            agent_id=None,
            max_depth=3,
        )
    )

    assert scoped is None
    assert org_wide is not None
    assert org_wide.root.memory_id == foreign_memory


@pytest.mark.asyncio
async def test_supersession_tip_stays_inside_the_callers_agent(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    """The tip field must not become a cross-agent id leak.

    A cross-agent supersedes edge is not written by any production path today,
    but the field is resolved by a separate helper, so it carries its own
    tenant and agent boundary instead of inheriting the walk's.
    """
    graph, root = await LineageGraph.seed(session_factory, "tip scope root")
    peer_agent = await graph.second_agent()
    peer = await graph.memory("peer successor", agent_id=peer_agent)
    await graph.link(peer, root)

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

    assert scoped is not None and org_wide is not None
    assert scoped.root.supersession_tip == root
    assert org_wide.root.supersession_tip == peer
