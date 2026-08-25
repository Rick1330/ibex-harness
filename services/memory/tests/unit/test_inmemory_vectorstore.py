from __future__ import annotations

from uuid import uuid4

import pytest

from app.vectorstore import InMemoryVectorStore, SearchHit, VectorStore


@pytest.mark.asyncio
async def test_inmemory_round_trip_and_ranking() -> None:
    store: VectorStore = InMemoryVectorStore()
    assert isinstance(store, InMemoryVectorStore)

    org = uuid4()
    agent = uuid4()
    mem_a = uuid4()
    mem_b = uuid4()
    store.bind_agent(mem_a, agent)
    store.bind_agent(mem_b, agent)

    query = [1.0] + [0.0] * 1023
    near = [0.9] + [0.0] * 1023
    far = [0.0] * 1023 + [1.0]

    await store.upsert(
        memory_id=mem_a,
        org_id=org,
        embedding=near,
        embedding_model="bge-m3",
    )
    await store.upsert(
        memory_id=mem_b,
        org_id=org,
        embedding=far,
        embedding_model="bge-m3",
    )

    hits = await store.search(
        org_id=org,
        agent_id=agent,
        query_embedding=query,
        limit=10,
        min_similarity=0.0,
    )
    assert len(hits) == 2
    assert hits[0].memory_id == mem_a
    assert hits[0].similarity > hits[1].similarity
    assert isinstance(hits[0], SearchHit)

    await store.delete(memory_id=mem_a, org_id=org)
    hits_after = await store.search(
        org_id=org,
        agent_id=agent,
        query_embedding=query,
        limit=10,
        min_similarity=0.0,
    )
    assert [h.memory_id for h in hits_after] == [mem_b]


@pytest.mark.asyncio
async def test_inmemory_respects_org_and_agent_scope() -> None:
    store = InMemoryVectorStore()
    org_a, org_b = uuid4(), uuid4()
    agent_a, agent_b = uuid4(), uuid4()
    mem = uuid4()
    store.bind_agent(mem, agent_a)
    vec = [1.0] + [0.0] * 1023
    await store.upsert(
        memory_id=mem, org_id=org_a, embedding=vec, embedding_model="bge-m3"
    )

    assert (
        await store.search(
            org_id=org_b, agent_id=agent_a, query_embedding=vec, limit=5, min_similarity=0.0
        )
        == []
    )
    assert (
        await store.search(
            org_id=org_a, agent_id=agent_b, query_embedding=vec, limit=5, min_similarity=0.0
        )
        == []
    )


@pytest.mark.asyncio
async def test_inmemory_validation_errors() -> None:
    store = InMemoryVectorStore()
    mem = uuid4()
    org = uuid4()
    with pytest.raises(KeyError):
        await store.upsert(
            memory_id=mem, org_id=org, embedding=[0.0] * 1024, embedding_model="bge-m3"
        )
    store.bind_agent(mem, uuid4())
    with pytest.raises(ValueError, match="embedding length"):
        await store.upsert(
            memory_id=mem, org_id=org, embedding=[0.0] * 8, embedding_model="bge-m3"
        )
    with pytest.raises(ValueError, match="1024"):
        await store.upsert(
            memory_id=mem,
            org_id=org,
            embedding=[0.0] * 512,
            embedding_model="bge-m3",
            embedding_dim=512,
        )
    with pytest.raises(ValueError, match="non-empty"):
        await store.upsert(
            memory_id=mem, org_id=org, embedding=[0.0] * 1024, embedding_model="  "
        )


@pytest.mark.asyncio
async def test_inmemory_delete_wrong_org_is_noop() -> None:
    store = InMemoryVectorStore()
    org_a, org_b = uuid4(), uuid4()
    agent = uuid4()
    mem = uuid4()
    store.bind_agent(mem, agent)
    vec = [1.0] + [0.0] * 1023
    await store.upsert(memory_id=mem, org_id=org_a, embedding=vec, embedding_model="bge-m3")
    await store.delete(memory_id=mem, org_id=org_b)
    hits = await store.search(
        org_id=org_a, agent_id=agent, query_embedding=vec, limit=5, min_similarity=0.0
    )
    assert len(hits) == 1
