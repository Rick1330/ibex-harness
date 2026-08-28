"""Integration tests for POST /v1/memories HTTP surface."""

from __future__ import annotations

import os
import secrets
from collections.abc import AsyncIterator
from typing import TYPE_CHECKING
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
from tests.integration.write_orchestrator_support import (
    EmbedProbe,
    OrchestratorTestDeps,
    build_orchestrator,
    ensure_pii_ready,
    set_content_hash,
)

if TYPE_CHECKING:
    from app.pii.service import PiiService

pytestmark = pytest.mark.integration

TOKEN = "test-memory-write-token"


async def pii_safe_content(
    prefix: str,
    pii: PiiService,
    *,
    attempts: int = 32,
) -> str:
    """Unique content verified clean by the real Presidio pipeline."""
    for _ in range(attempts):
        candidate = f"{prefix} ref {secrets.token_hex(8)}"
        if not (await pii.process_async(candidate)).pii_detected:
            return candidate
    pytest.fail("could not generate Presidio-clean integration content")


def _redis_url() -> str | None:
    return os.getenv("IBEX_MEMORY_REDIS_URL") or os.getenv("REDIS_URL")


@pytest.fixture
async def http_context(
    session_factory: async_sessionmaker[AsyncSession],
    settings: Settings,
    store,
) -> AsyncIterator[tuple[AsyncClient, object, object, object, PiiService]]:
    probe = EmbedProbe()
    redis_url = _redis_url()
    cfg = settings.model_copy(update={"redis_url": redis_url}) if redis_url else settings
    orch = build_orchestrator(OrchestratorTestDeps(session_factory, cfg, store, embed=probe))
    pii: PiiService = orch._pipeline._stages[1]._pii
    await ensure_pii_ready(orch)

    org_id, agent_id, _ = await seed_org_agent_memory(
        session_factory, content=await pii_safe_content("http seed", pii)
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
                yield client, org_id, agent_id, probe, pii
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
    client, org_id, agent_id, _probe, pii = http_context
    content = await pii_safe_content("Novel HTTP write", pii)
    response = await client.post(
        "/v1/memories",
        headers={"Authorization": f"Bearer {TOKEN}"},
        json={"agent_id": str(agent_id), "content": content},
    )
    assert response.status_code == 201, response.text
    body = response.json()
    assert body["data"]["org_id"] == str(org_id)
    assert body["data"]["content"] == content
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
    pii: PiiService = orch._pipeline._stages[1]._pii
    await ensure_pii_ready(orch)

    content = await pii_safe_content("Duplicate HTTP payload", pii)
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

    client, org_id, agent_id, _probe, pii = http_context
    content = await pii_safe_content("Redis cache test", pii)
    response = await client.post(
        "/v1/memories",
        headers={"Authorization": f"Bearer {TOKEN}"},
        json={"agent_id": str(agent_id), "content": content},
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
    client, _org_id, agent_id, _probe, _pii = http_context
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
        json={"agent_id": str(agent_id), "content": f"broken redis {uuid4().hex}"},
    )
    assert response.status_code == 201


@pytest.mark.asyncio
async def test_idempotency_replay(http_context) -> None:
    if not _redis_url():
        pytest.skip("REDIS_URL not set")

    client, _org_id, agent_id, _probe, pii = http_context
    key = str(uuid4())
    headers = {
        "Authorization": f"Bearer {TOKEN}",
        "X-Idempotency-Key": key,
    }
    body = {
        "agent_id": str(agent_id),
        "content": await pii_safe_content("Idempotent write", pii),
    }
    first = await client.post("/v1/memories", headers=headers, json=body)
    assert first.status_code == 201
    second = await client.post("/v1/memories", headers=headers, json=body)
    assert second.status_code == 201
    assert second.headers.get("x-idempotency-replayed") == "true"
    assert first.json()["data"]["id"] == second.json()["data"]["id"]
