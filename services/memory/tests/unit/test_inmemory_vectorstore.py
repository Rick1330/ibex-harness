from __future__ import annotations

from uuid import uuid4

import pytest

from app.vectorstore import (
    InMemoryVectorStore,
    SearchHit,
    SearchRequest,
    UpsertRequest,
    VectorStore,
)


def _upsert(
    memory_id,
    org_id,
    embedding,
    *,
    embedding_model: str = "bge-m3",
    embedding_dim: int = 1024,
) -> UpsertRequest:
    return UpsertRequest(
        memory_id=memory_id,
        org_id=org_id,
        embedding=embedding,
        embedding_model=embedding_model,
        embedding_dim=embedding_dim,
    )


def _search(org_id, agent_id, query, *, limit: int = 10, min_similarity: float = 0.0) -> SearchRequest:
    return SearchRequest(
        org_id=org_id,
        agent_id=agent_id,
        query_embedding=query,
        limit=limit,
        min_similarity=min_similarity,
    )


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

    await store.upsert(_upsert(mem_a, org, near))
    await store.upsert(_upsert(mem_b, org, far))

    hits = await store.search(_search(org, agent, query))
    assert len(hits) == 2
    assert hits[0].memory_id == mem_a
    assert hits[0].similarity > hits[1].similarity
    assert isinstance(hits[0], SearchHit)

    await store.delete(memory_id=mem_a, org_id=org)
    hits_after = await store.search(_search(org, agent, query))
    assert [h.memory_id for h in hits_after] == [mem_b]


@pytest.mark.asyncio
async def test_inmemory_respects_org_and_agent_scope() -> None:
    store = InMemoryVectorStore()
    org_a, org_b = uuid4(), uuid4()
    agent_a, agent_b = uuid4(), uuid4()
    mem = uuid4()
    store.bind_agent(mem, agent_a)
    vec = [1.0] + [0.0] * 1023
    await store.upsert(_upsert(mem, org_a, vec))

    assert await store.search(_search(org_b, agent_a, vec, limit=5)) == []
    assert await store.search(_search(org_a, agent_b, vec, limit=5)) == []


@pytest.mark.asyncio
async def test_inmemory_validation_errors() -> None:
    store = InMemoryVectorStore()
    mem = uuid4()
    org = uuid4()
    with pytest.raises(KeyError):
        await store.upsert(_upsert(mem, org, [0.0] * 1024))
    store.bind_agent(mem, uuid4())
    with pytest.raises(ValueError, match="embedding length"):
        await store.upsert(_upsert(mem, org, [0.0] * 8))
    with pytest.raises(ValueError, match="1024"):
        await store.upsert(_upsert(mem, org, [0.0] * 512, embedding_dim=512))
    with pytest.raises(ValueError, match="non-empty"):
        await store.upsert(_upsert(mem, org, [0.0] * 1024, embedding_model="  "))


@pytest.mark.asyncio
async def test_inmemory_delete_wrong_org_is_noop() -> None:
    store = InMemoryVectorStore()
    org_a, org_b = uuid4(), uuid4()
    agent = uuid4()
    mem = uuid4()
    store.bind_agent(mem, agent)
    vec = [1.0] + [0.0] * 1023
    await store.upsert(_upsert(mem, org_a, vec))
    await store.delete(memory_id=mem, org_id=org_b)
    hits = await store.search(_search(org_a, agent, vec, limit=5))
    assert len(hits) == 1
