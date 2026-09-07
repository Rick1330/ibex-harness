"""Unit tests for MCP calendar-minute Redis rate limiter."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock
from uuid import UUID, uuid4

import pytest
from redis.exceptions import RedisError

from app.ratelimit import (
    INCR_EXPIRE_LUA,
    KEY_TTL_SECONDS,
    NoopMcpLimiter,
    RedisMcpLimiter,
    build_mcp_rate_limiter,
    parse_org_rpm_overrides,
)

ORG = UUID("aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa")
ORG_B = UUID("bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb")


def test_parse_org_rpm_overrides() -> None:
    assert parse_org_rpm_overrides("") == {}
    assert parse_org_rpm_overrides(f"{ORG}=10,{ORG_B}=20") == {ORG: 10, ORG_B: 20}


def test_parse_org_rpm_overrides_rejects_bad() -> None:
    with pytest.raises(ValueError, match="expected uuid=rpm"):
        parse_org_rpm_overrides("not-a-pair")
    with pytest.raises(ValueError, match="invalid org UUID"):
        parse_org_rpm_overrides("nope=10")
    with pytest.raises(ValueError, match="invalid RPM"):
        parse_org_rpm_overrides(f"{ORG}=0")


def test_lua_script_mirrors_go_semantics() -> None:
    assert "INCR" in INCR_EXPIRE_LUA
    assert "EXPIRE" in INCR_EXPIRE_LUA
    assert "n == 1" in INCR_EXPIRE_LUA
    assert KEY_TTL_SECONDS == 90


def test_redis_key_uses_mcp_segment() -> None:
    key = RedisMcpLimiter.redis_key(ORG, unix_minute=12345)
    assert key == f"ratelimit:{ORG}:mcp:12345"
    assert ":rpm:" not in key


@pytest.mark.asyncio
async def test_noop_always_allows() -> None:
    limiter = NoopMcpLimiter(default_rpm=5)
    for _ in range(20):
        result = await limiter.check(ORG)
        assert result.allowed is True


@pytest.mark.asyncio
async def test_redis_limiter_rejects_over_limit() -> None:
    script = AsyncMock(side_effect=[1, 2, 3])
    redis = MagicMock()
    redis.register_script.return_value = script
    limiter = RedisMcpLimiter(redis, default_rpm=2, owned=False)

    first = await limiter.check(ORG)
    second = await limiter.check(ORG)
    third = await limiter.check(ORG)

    assert first.allowed is True
    assert second.allowed is True
    assert third.allowed is False
    assert third.remaining == 0
    assert script.await_count == 3
    # EXPIRE TTL passed as script ARGV
    assert script.await_args_list[0].kwargs["args"] == [KEY_TTL_SECONDS]


@pytest.mark.asyncio
async def test_redis_limiter_org_override() -> None:
    script = AsyncMock(side_effect=[1, 2])
    redis = MagicMock()
    redis.register_script.return_value = script
    limiter = RedisMcpLimiter(
        redis, default_rpm=100, org_overrides={ORG: 1}, owned=False
    )
    assert (await limiter.check(ORG)).allowed is True
    assert (await limiter.check(ORG)).allowed is False


@pytest.mark.asyncio
async def test_redis_limiter_fail_open_on_error() -> None:
    script = AsyncMock(side_effect=RedisError("down"))
    redis = MagicMock()
    redis.register_script.return_value = script
    limiter = RedisMcpLimiter(redis, default_rpm=1, owned=False)
    result = await limiter.check(ORG)
    assert result.allowed is True


def test_build_noop_when_redis_unset() -> None:
    limiter = build_mcp_rate_limiter(redis_url="", default_rpm=120, org_overrides={})
    assert isinstance(limiter, NoopMcpLimiter)


@pytest.mark.asyncio
async def test_build_redis_when_url_set() -> None:
    # from_url will not connect until a command; construct then aclose.
    limiter = build_mcp_rate_limiter(
        redis_url="redis://127.0.0.1:9/0",
        default_rpm=10,
        org_overrides={uuid4(): 3},
    )
    assert isinstance(limiter, RedisMcpLimiter)
    await limiter.aclose()
