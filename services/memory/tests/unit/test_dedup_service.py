"""Unit tests for DedupService exact + near-duplicate logic."""

from __future__ import annotations

from uuid import UUID, uuid4

import pytest

from app.config import Settings
from app.dedup.hash import content_hash_sha256
from app.dedup.service import DedupService
from app.vectorstore.base import UpsertRequest
from app.vectorstore.memory import InMemoryVectorStore


def _axis(i: int) -> list[float]:
    vec = [0.0] * 1024
    vec[i] = 1.0
    return vec


@pytest.mark.asyncio
async def test_exact_miss_returns_hash_only() -> None:
    lookups: list[tuple[UUID, UUID, str]] = []

    async def lookup(org_id: UUID, agent_id: UUID, content_hash: str) -> UUID | None:
        lookups.append((org_id, agent_id, content_hash))
        return None

    svc = DedupService(Settings(), exact_lookup=lookup)
    org, agent = uuid4(), uuid4()
    result = await svc.check_exact(org_id=org, agent_id=agent, content="Hello World")
    assert result.is_exact_duplicate is False
    assert result.existing_memory_id is None
    assert result.content_hash == content_hash_sha256("Hello World")
    assert len(lookups) == 1


@pytest.mark.asyncio
async def test_exact_hit_bumps_and_returns_id() -> None:
    existing = uuid4()
    bumps: list[tuple[UUID, UUID]] = []

    async def lookup(_org_id: UUID, _agent_id: UUID, _content_hash: str) -> UUID | None:
        return existing

    async def bump(org_id: UUID, memory_id: UUID) -> int:
        bumps.append((org_id, memory_id))
        return 3

    svc = DedupService(Settings(), exact_lookup=lookup, bump_retrieval=bump)
    org, agent = uuid4(), uuid4()
    result = await svc.check_exact(org_id=org, agent_id=agent, content="same")
    assert result.is_exact_duplicate is True
    assert result.existing_memory_id == existing
    assert bumps == [(org, existing)]


@pytest.mark.asyncio
async def test_exact_hit_requires_bump_callback() -> None:
    existing = uuid4()

    async def lookup(_org_id: UUID, _agent_id: UUID, _content_hash: str) -> UUID | None:
        return existing

    svc = DedupService(Settings(), exact_lookup=lookup)
    with pytest.raises(RuntimeError, match="bump_retrieval required"):
        await svc.check_exact(org_id=uuid4(), agent_id=uuid4(), content="same")


@pytest.mark.asyncio
async def test_exact_disabled_skips_lookup() -> None:
    called = False

    async def lookup(_org_id: UUID, _agent_id: UUID, _content_hash: str) -> UUID | None:
        nonlocal called
        called = True
        return None

    svc = DedupService(Settings(dedup_exact_enabled=False), exact_lookup=lookup)
    result = await svc.check_exact(org_id=uuid4(), agent_id=uuid4(), content="x")
    assert called is False
    assert result.is_exact_duplicate is False
    assert result.content_hash == content_hash_sha256("x")


@pytest.mark.asyncio
async def test_near_dup_uses_vector_store_and_strict_gt() -> None:
    store = InMemoryVectorStore()
    org, agent = uuid4(), uuid4()
    near_id = uuid4()
    far_id = uuid4()
    store.bind_agent(near_id, agent)
    store.bind_agent(far_id, agent)

    await store.upsert(
        UpsertRequest(
            memory_id=near_id,
            org_id=org,
            embedding=_axis(0),
            embedding_model="test",
        )
    )
    await store.upsert(
        UpsertRequest(
            memory_id=far_id,
            org_id=org,
            embedding=_axis(2),
            embedding_model="test",
        )
    )

    svc = DedupService(
        Settings(near_duplicate_sim_threshold=0.92, near_duplicate_candidate_limit=10),
        store=store,
    )
    candidates = await svc.find_near_duplicates(
        org_id=org, agent_id=agent, embedding=_axis(0)
    )
    assert near_id in candidates
    assert far_id not in candidates


@pytest.mark.asyncio
async def test_near_dup_excludes_exact_threshold() -> None:
    """VectorStore.search uses >=; near-dup keeps only similarity > threshold."""

    class _BoundaryStore(InMemoryVectorStore):
        async def search(self, request):  # type: ignore[no-untyped-def]
            from app.vectorstore.base import SearchHit

            _ = request
            return [
                SearchHit(memory_id=uuid4(), similarity=0.92),
                SearchHit(memory_id=uuid4(), similarity=0.921),
            ]

    store = _BoundaryStore()
    svc = DedupService(Settings(near_duplicate_sim_threshold=0.92), store=store)
    candidates = await svc.find_near_duplicates(
        org_id=uuid4(), agent_id=uuid4(), embedding=_axis(0)
    )
    assert len(candidates) == 1


@pytest.mark.asyncio
async def test_exact_requires_lookup_when_enabled() -> None:
    svc = DedupService(Settings(dedup_exact_enabled=True))
    with pytest.raises(RuntimeError, match="exact_lookup required"):
        await svc.check_exact(org_id=uuid4(), agent_id=uuid4(), content="x")


@pytest.mark.asyncio
async def test_near_requires_store() -> None:
    svc = DedupService(Settings())
    with pytest.raises(RuntimeError, match="VectorStore required"):
        await svc.find_near_duplicates(
            org_id=uuid4(), agent_id=uuid4(), embedding=_axis(0)
        )

    store = InMemoryVectorStore()
    svc = DedupService(Settings(near_duplicate_sim_threshold=0.92), store=store)
    candidates = await svc.find_near_duplicates(
        org_id=uuid4(),
        agent_id=uuid4(),
        embedding=_axis(0),
    )
    assert candidates == []


@pytest.mark.asyncio
async def test_near_dup_org_scoped() -> None:
    store = InMemoryVectorStore()
    org_a, org_b, agent = uuid4(), uuid4(), uuid4()
    mem = uuid4()
    store.bind_agent(mem, agent)
    vec = _axis(0)
    await store.upsert(
        UpsertRequest(memory_id=mem, org_id=org_a, embedding=vec, embedding_model="t")
    )
    svc = DedupService(Settings(near_duplicate_sim_threshold=0.50), store=store)
    assert await svc.find_near_duplicates(org_id=org_a, agent_id=agent, embedding=vec) == [
        mem
    ]
    assert await svc.find_near_duplicates(org_id=org_b, agent_id=agent, embedding=vec) == []
