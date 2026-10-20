"""Live-Redis tests for the operator limiter (AGENTS.md §9: no Lua mocks)."""

from __future__ import annotations

import os
from uuid import uuid4

import pytest
from mcp_gateway import RateLimitUnavailableError
from redis.asyncio import Redis

from app.ratelimit import KEY_TTL_SECONDS, RedisOperatorLimiter

pytestmark = pytest.mark.integration

_ENV_CANDIDATES = (
    "IBEX_MCP_OPERATOR_TEST_REDIS_URL",
    "REDIS_TEST_URL",
)


def _redis_url() -> str:
    for name in _ENV_CANDIDATES:
        value = os.environ.get(name, "").strip()
        if value:
            return value
    pytest.skip("no Redis URL configured for operator integration tests")


@pytest.fixture
async def redis() -> Redis:
    client = Redis.from_url(_redis_url(), decode_responses=True)
    try:
        yield client
    finally:
        await client.aclose()


async def _cleanup(redis: Redis, org_id) -> None:
    async for key in redis.scan_iter(match=f"ratelimit:{org_id}:mcp_operator:*"):
        await redis.delete(key)


async def test_shared_counter_rejects_after_org_limit(redis: Redis) -> None:
    org = uuid4()
    limiter = RedisOperatorLimiter(redis, default_rpm=2, owned=False, fail_closed=True)
    try:
        assert (await limiter.check(org)).allowed is True
        assert (await limiter.check(org)).allowed is True
        rejected = await limiter.check(org)
        assert rejected.allowed is False
        assert rejected.remaining == 0
    finally:
        await _cleanup(redis, org)


async def test_counter_is_shared_across_limiter_instances(redis: Redis) -> None:
    org = uuid4()
    first = RedisOperatorLimiter(redis, default_rpm=2, owned=False, fail_closed=True)
    second = RedisOperatorLimiter(redis, default_rpm=2, owned=False, fail_closed=True)
    try:
        await first.check(org)
        await first.check(org)
        assert (await second.check(org)).allowed is False
    finally:
        await _cleanup(redis, org)


async def test_counter_expires_on_the_window(redis: Redis) -> None:
    org = uuid4()
    limiter = RedisOperatorLimiter(redis, default_rpm=5, owned=False, fail_closed=True)
    try:
        await limiter.check(org)
        key = limiter.redis_key(org)
        ttl = await redis.ttl(key)
        assert 0 < ttl <= KEY_TTL_SECONDS
    finally:
        await _cleanup(redis, org)


async def test_counters_are_isolated_by_org(redis: Redis) -> None:
    org_a = uuid4()
    org_b = uuid4()
    limiter = RedisOperatorLimiter(redis, default_rpm=1, owned=False, fail_closed=True)
    try:
        assert (await limiter.check(org_a)).allowed is True
        assert (await limiter.check(org_a)).allowed is False
        assert (await limiter.check(org_b)).allowed is True
    finally:
        await _cleanup(redis, org_a)
        await _cleanup(redis, org_b)


async def test_unavailable_store_fails_closed() -> None:
    unavailable = Redis.from_url(
        "redis://127.0.0.1:1/0",
        decode_responses=True,
        socket_connect_timeout=0.2,
        socket_timeout=0.2,
    )
    limiter = RedisOperatorLimiter(unavailable, default_rpm=5, owned=True, fail_closed=True)
    try:
        with pytest.raises(RateLimitUnavailableError):
            await limiter.check(uuid4())
    finally:
        await limiter.aclose()
