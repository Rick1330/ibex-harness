from __future__ import annotations

from collections.abc import Callable
from uuid import UUID, uuid4

import pytest

from app.vectorstore import (
    InMemoryVectorStore,
    SearchHit,
    SearchRequest,
    UpsertRequest,
    VectorStore,
)

_ZERO = [0.0] * 1024
_UNIT = [1.0] + [0.0] * 1023


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

    query = _UNIT
    near = [0.9] + [0.0] * 1023
    far = [0.0] * 1023 + [1.0]

    await store.upsert(
        UpsertRequest(memory_id=mem_a, org_id=org, embedding=near, embedding_model="bge-m3")
    )
    await store.upsert(
        UpsertRequest(memory_id=mem_b, org_id=org, embedding=far, embedding_model="bge-m3")
    )

    hits = await store.search(
        SearchRequest(
            org_id=org, agent_id=agent, query_embedding=query, limit=10, min_similarity=0.0
        )
    )
    assert len(hits) == 2
    assert hits[0].memory_id == mem_a
    assert hits[0].similarity > hits[1].similarity
    assert isinstance(hits[0], SearchHit)

    await store.delete(memory_id=mem_a, org_id=org)
    hits_after = await store.search(
        SearchRequest(
            org_id=org, agent_id=agent, query_embedding=query, limit=10, min_similarity=0.0
        )
    )
    assert [h.memory_id for h in hits_after] == [mem_b]


@pytest.mark.asyncio
async def test_inmemory_respects_org_and_agent_scope() -> None:
    store = InMemoryVectorStore()
    org_a, org_b = uuid4(), uuid4()
    agent_a, agent_b = uuid4(), uuid4()
    mem = uuid4()
    store.bind_agent(mem, agent_a)
    await store.upsert(
        UpsertRequest(memory_id=mem, org_id=org_a, embedding=_UNIT, embedding_model="bge-m3")
    )

    assert (
        await store.search(
            SearchRequest(
                org_id=org_b, agent_id=agent_a, query_embedding=_UNIT, limit=5, min_similarity=0.0
            )
        )
        == []
    )
    assert (
        await store.search(
            SearchRequest(
                org_id=org_a, agent_id=agent_b, query_embedding=_UNIT, limit=5, min_similarity=0.0
            )
        )
        == []
    )


@pytest.mark.asyncio
async def test_inmemory_rejects_agent_rebind_after_upsert() -> None:
    store = InMemoryVectorStore()
    mem, org = uuid4(), uuid4()
    agent_a, agent_b = uuid4(), uuid4()
    store.bind_agent(mem, agent_a)
    await store.upsert(
        UpsertRequest(memory_id=mem, org_id=org, embedding=_UNIT, embedding_model="bge-m3")
    )
    with pytest.raises(ValueError, match="cannot rebind"):
        store.bind_agent(mem, agent_b)


@pytest.mark.asyncio
async def test_inmemory_rejects_cross_org_upsert() -> None:
    store = InMemoryVectorStore()
    org_a, org_b = uuid4(), uuid4()
    agent_a = uuid4()
    mem = uuid4()
    store.bind_agent(mem, agent_a)
    await store.upsert(
        UpsertRequest(memory_id=mem, org_id=org_a, embedding=_UNIT, embedding_model="bge-m3")
    )
    request = UpsertRequest(
        memory_id=mem, org_id=org_b, embedding=_UNIT, embedding_model="bge-m3"
    )
    with pytest.raises(LookupError, match="not found for org"):
        await store.upsert(request)
    foreign = await store.search(
        SearchRequest(
            org_id=org_b, agent_id=agent_a, query_embedding=_UNIT, limit=5, min_similarity=0.0
        )
    )
    owned = await store.search(
        SearchRequest(
            org_id=org_a, agent_id=agent_a, query_embedding=_UNIT, limit=5, min_similarity=0.0
        )
    )
    assert foreign == []
    assert len(owned) == 1


@pytest.mark.parametrize(
    ("bind_first", "build", "exc_type", "match"),
    [
        (
            False,
            lambda mem, org: UpsertRequest(
                memory_id=mem, org_id=org, embedding=_ZERO, embedding_model="bge-m3"
            ),
            KeyError,
            None,
        ),
        (
            True,
            lambda mem, org: UpsertRequest(
                memory_id=mem, org_id=org, embedding=[0.0] * 8, embedding_model="bge-m3"
            ),
            ValueError,
            "embedding length",
        ),
        (
            True,
            lambda mem, org: UpsertRequest(
                memory_id=mem,
                org_id=org,
                embedding=[0.0] * 512,
                embedding_model="bge-m3",
                embedding_dim=512,
            ),
            ValueError,
            "1024",
        ),
        (
            True,
            lambda mem, org: UpsertRequest(
                memory_id=mem, org_id=org, embedding=_ZERO, embedding_model="  "
            ),
            ValueError,
            "non-empty",
        ),
    ],
    ids=["needs-bind", "short-embedding", "wrong-dim", "blank-model"],
)
@pytest.mark.asyncio
async def test_inmemory_upsert_validation(
    bind_first: bool,
    build: Callable[[UUID, UUID], UpsertRequest],
    exc_type: type[BaseException],
    match: str | None,
) -> None:
    store = InMemoryVectorStore()
    mem, org = uuid4(), uuid4()
    if bind_first:
        store.bind_agent(mem, uuid4())
    request = build(mem, org)
    with pytest.raises(exc_type, match=match):
        await store.upsert(request)


@pytest.mark.asyncio
async def test_search_rejects_invalid_limit_parity() -> None:
    store = InMemoryVectorStore()
    org, agent, mem = uuid4(), uuid4(), uuid4()
    store.bind_agent(mem, agent)
    await store.upsert(
        UpsertRequest(memory_id=mem, org_id=org, embedding=_UNIT, embedding_model="bge-m3")
    )
    request = SearchRequest(org_id=org, agent_id=agent, query_embedding=_UNIT, limit=0)
    with pytest.raises(ValueError, match="limit must be >= 1"):
        await store.search(request)


def test_search_request_rejects_invalid_iterative_scan() -> None:
    org, agent = uuid4(), uuid4()
    request = SearchRequest(
        org_id=org,
        agent_id=agent,
        query_embedding=_UNIT,
        limit=5,
        iterative_scan="bogus",
    )
    with pytest.raises(ValueError, match="iterative_scan"):
        request.validate()


@pytest.mark.asyncio
async def test_inmemory_delete_wrong_org_is_noop() -> None:
    store = InMemoryVectorStore()
    org_a, org_b = uuid4(), uuid4()
    agent = uuid4()
    mem = uuid4()
    store.bind_agent(mem, agent)
    await store.upsert(
        UpsertRequest(memory_id=mem, org_id=org_a, embedding=_UNIT, embedding_model="bge-m3")
    )
    await store.delete(memory_id=mem, org_id=org_b)
    hits = await store.search(
        SearchRequest(
            org_id=org_a, agent_id=agent, query_embedding=_UNIT, limit=5, min_similarity=0.0
        )
    )
    assert len(hits) == 1
