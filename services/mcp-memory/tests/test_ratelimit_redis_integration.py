"""Real-Redis integration for MCP calendar-minute Lua limiter.

Uses compose-test Redis (localhost:6380) by default, or IBEX_MCP_TEST_REDIS_URL
/ REDIS_URL when set (CI service container on :6379).
"""

from __future__ import annotations

import asyncio
import os
from uuid import uuid4

import pytest
import redis as redis_sync
from redis.asyncio import Redis
from redis.exceptions import RedisError

from app.ratelimit import KEY_TTL_SECONDS, RedisMcpLimiter

pytestmark = pytest.mark.integration

# Prefer dedicated test URL so unit Settings() is not polluted by REDIS_URL.
_REDIS_URL = os.environ.get(
    "IBEX_MCP_TEST_REDIS_URL",
    os.environ.get("REDIS_URL", "redis://127.0.0.1:6380/0"),
)


@pytest.fixture(scope="module")
def require_redis() -> str:
    client = redis_sync.Redis.from_url(
        _REDIS_URL,
        socket_connect_timeout=0.3,
        socket_timeout=0.3,
    )
    try:
        client.ping()
    except (RedisError, OSError, TimeoutError):
        pytest.skip(f"Redis not available at {_REDIS_URL}")
    finally:
        client.close()
    return _REDIS_URL


@pytest.mark.asyncio
async def test_redis_limiter_live_reject_ttl_and_concurrency(require_redis: str) -> None:
    org = uuid4()
    org_b = uuid4()
    client: Redis = Redis.from_url(require_redis, decode_responses=True)
    limiter = RedisMcpLimiter(client, default_rpm=3, owned=True)
    key = RedisMcpLimiter.redis_key(org)
    key_b = RedisMcpLimiter.redis_key(org_b)
    try:
        await client.delete(key, key_b)

        allowed = [await limiter.check(org) for _ in range(3)]
        assert all(r.allowed for r in allowed)
        rejected = await limiter.check(org)
        assert rejected.allowed is False
        assert rejected.remaining == 0

        ttl = await client.ttl(key)
        assert 0 < ttl <= KEY_TTL_SECONDS

        # Concurrent INCR must stay atomic (no lost updates under load).
        burst = await asyncio.gather(*[limiter.check(org_b) for _ in range(20)])
        assert sum(1 for r in burst if r.allowed) == 3
        assert sum(1 for r in burst if not r.allowed) == 17
        assert int(await client.get(key_b) or 0) == 20
    finally:
        await client.delete(key, key_b)
        await limiter.aclose()
