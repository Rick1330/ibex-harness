"""Integration tests for POST /v1/memories HTTP surface."""

from __future__ import annotations

import os
from collections.abc import AsyncIterator
from uuid import uuid4

import pytest
from httpx import ASGITransport, AsyncClient
from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.auth.client import StaticTokenValidator, ValidateResult
from app.config import Settings
from app.main import create_app
from app.permissions import MEMORY_WRITE
from tests.integration.conftest import seed_org_agent_memory
from tests.integration.http_pii_fixtures import (
    HTTP_DUPLICATE_PAYLOAD_CONTENT,
    HTTP_IDEMPOTENT_WRITE_CONTENT,
    HTTP_NOVEL_WRITE_CONTENT,
    HTTP_REDIS_CACHE_CONTENT,
    HTTP_SEED_CONTENT,
    HTTP_BROKEN_REDIS_WRITE_CONTENT,
)
from tests.integration.write_orchestrator_support import (
    EmbedProbe,
    OrchestratorTestDeps,
    build_orchestrator,
    ensure_pii_ready,
    set_content_hash,
)

pytestmark = pytest.mark.integration

TOKEN = "test-memory-write-token"


def _redis_url() -> str | None:
    return os.getenv("IBEX_MEMORY_REDIS_URL") or os.getenv("REDIS_URL")


@pytest.fixture
async def http_context(
    session_factory: async_sessionmaker[AsyncSession],
    settings: Settings,
    store,
) -> AsyncIterator[tuple[AsyncClient, object, object, object]]:
    probe = EmbedProbe()
    redis_url = _redis_url()
    cfg = settings.model_copy(update={"redis_url": redis_url}) if redis_url else settings
    orch = build_orchestrator(OrchestratorTestDeps(session_factory, cfg, store, embed=probe))
    await ensure_pii_ready(orch)

    org_id, agent_id, _ = await seed_org_agent_memory(
        session_factory, content=HTTP_SEED_CONTENT
    )
    validator = StaticTokenValidator(
        {
            TOKEN: ValidateResult(
                org_id=org_id,
                permissions=MEMORY_WRITE,
                agent_id=agent_id,
            )
        }
    )
    redis_client: Redis | None = None
    try:
        if redis_url:
            from app.write.after_commit import AfterCommitHandler
            from app.write.cache import MemoryCacheWriter

            redis_client = Redis.from_url(redis_url)
            after_commit = AfterCommitHandler(
                cache=MemoryCacheWriter(redis_client, cfg),
                store=store,
            ).__call__
            orch._after_commit = after_commit

        app = create_app(settings=cfg, validator=validator)
        async with app.router.lifespan_context(app):
            app.state.memory.write_orchestrator = orch
            transport = ASGITransport(app=app)
            async with AsyncClient(transport=transport, base_url="http://test") as client:
                yield client, org_id, agent_id, probe
    finally:
        if redis_client is not None:
            await redis_client.aclose()


@pytest.mark.asyncio
async def test_create_memory_requires_auth(
    session_factory: async_sessionmaker[AsyncSession],
    settings: Settings,
) -> None:
    app = create_app(settings=settings)
    async with app.router.lifespan_context(app):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.post(
                "/v1/memories",
                json={"agent_id": str(uuid4()), "content": "No auth header"},
            )
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_create_memory_happy_path_201(http_context) -> None:
    client, org_id, agent_id, _probe = http_context
    response = await client.post(
        "/v1/memories",
        headers={"Authorization": f"Bearer {TOKEN}"},
        json={"agent_id": str(agent_id), "content": HTTP_NOVEL_WRITE_CONTENT},
    )
    assert response.status_code == 201, response.text
    body = response.json()
    assert body["data"]["org_id"] == str(org_id)
    assert body["data"]["content"] == HTTP_NOVEL_WRITE_CONTENT
    assert body["meta"]["deduplication"]["is_duplicate"] is False


@pytest.mark.asyncio
async def test_create_memory_duplicate_409(
    session_factory: async_sessionmaker[AsyncSession],
    settings: Settings,
    store,
) -> None:
    from app.dedup.hash import content_hash_sha256

    probe = EmbedProbe()
    orch = build_orchestrator(OrchestratorTestDeps(session_factory, settings, store, embed=probe))
    await ensure_pii_ready(orch)

    content = HTTP_DUPLICATE_PAYLOAD_CONTENT
    digest = content_hash_sha256(content)
    org_id, agent_id, memory_id = await seed_org_agent_memory(
        session_factory, content=content
    )
    await set_content_hash(
        session_factory,
        org_id=org_id,
        memory_id=memory_id,
        content_hash=digest,
    )
    validator = StaticTokenValidator(
        {
            TOKEN: ValidateResult(
                org_id=org_id,
                permissions=MEMORY_WRITE,
                agent_id=agent_id,
            )
        }
    )

    app = create_app(settings=settings, validator=validator)
    async with app.router.lifespan_context(app):
        app.state.memory.write_orchestrator = orch
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.post(
                "/v1/memories",
                headers={"Authorization": f"Bearer {TOKEN}"},
                json={"agent_id": str(agent_id), "content": content},
            )
    assert response.status_code == 409
    detail = response.json()["detail"]
    assert detail["code"] == "DUPLICATE_CONTENT"
    assert detail["existing_memory_id"] == str(memory_id)


@pytest.mark.asyncio
async def test_create_memory_redis_cache_populated(http_context) -> None:
    redis_url = _redis_url()
    if not redis_url:
        pytest.skip("REDIS_URL not set")

    client, org_id, agent_id, _probe = http_context
    response = await client.post(
        "/v1/memories",
        headers={"Authorization": f"Bearer {TOKEN}"},
        json={"agent_id": str(agent_id), "content": HTTP_REDIS_CACHE_CONTENT},
    )
    assert response.status_code == 201, response.text
    memory_id = response.json()["data"]["id"]
    redis = Redis.from_url(redis_url)
    try:
        cached = await redis.get(f"{org_id}:memory:{memory_id}")
        assert cached is not None
    finally:
        await redis.aclose()


@pytest.mark.asyncio
async def test_cache_failure_does_not_fail_write(
    http_context,
    settings: Settings,
    store,
) -> None:
    client, _org_id, agent_id, _probe = http_context
    transport: ASGITransport = client._transport  # type: ignore[assignment]
    app = transport.app
    orch = app.state.memory.write_orchestrator

    class _BrokenRedis:
        async def set(self, *_args, **_kwargs):
            raise OSError("redis down")

        async def zadd(self, *_args, **_kwargs):
            raise OSError("redis down")

        async def expire(self, *_args, **_kwargs):
            raise OSError("redis down")

    from app.write.after_commit import AfterCommitHandler
    from app.write.cache import MemoryCacheWriter

    broken = AfterCommitHandler(
        cache=MemoryCacheWriter(_BrokenRedis(), settings),  # type: ignore[arg-type]
        store=store,
    )
    orch._after_commit = broken.__call__
    response = await client.post(
        "/v1/memories",
        headers={"Authorization": f"Bearer {TOKEN}"},
        json={
            "agent_id": str(agent_id),
            "content": HTTP_BROKEN_REDIS_WRITE_CONTENT,
        },
    )
    assert response.status_code == 201


@pytest.mark.asyncio
async def test_idempotency_replay(http_context) -> None:
    if not _redis_url():
        pytest.skip("REDIS_URL not set")

    client, _org_id, agent_id, _probe = http_context
    key = str(uuid4())
    headers = {
        "Authorization": f"Bearer {TOKEN}",
        "X-Idempotency-Key": key,
    }
    body = {
        "agent_id": str(agent_id),
        "content": HTTP_IDEMPOTENT_WRITE_CONTENT,
    }
    first = await client.post("/v1/memories", headers=headers, json=body)
    assert first.status_code == 201
    second = await client.post("/v1/memories", headers=headers, json=body)
    assert second.status_code == 201
    assert second.headers.get("x-idempotency-replayed") == "true"
    assert first.json()["data"]["id"] == second.json()["data"]["id"]
