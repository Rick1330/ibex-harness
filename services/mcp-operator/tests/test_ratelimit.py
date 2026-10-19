"""Org calendar-minute limiter for the operator gateway."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock
from uuid import UUID, uuid4

import pytest
from mcp_gateway import RateLimitUnavailableError
from redis.exceptions import RedisError

from app.ratelimit import (
    INCR_EXPIRE_LUA,
    KEY_TTL_SECONDS,
    NoopOperatorLimiter,
    OperatorRateLimiter,
    RedisOperatorLimiter,
    build_operator_rate_limiter,
    parse_org_rpm_overrides,
)

ORG = UUID("aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa")
ORG_B = UUID("bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb")


def test_parse_org_rpm_overrides() -> None:
    assert parse_org_rpm_overrides("") == {}
    assert parse_org_rpm_overrides(f"{ORG}=10,{ORG_B}=20") == {ORG: 10, ORG_B: 20}
    assert parse_org_rpm_overrides(f" , {ORG}=7, ") == {ORG: 7}


@pytest.mark.parametrize(
    ("raw", "match"),
    [
        ("not-a-pair", "expected uuid=rpm"),
        ("nope=10", "invalid org UUID"),
        (f"{ORG}=0", "invalid RPM"),
        (f"{ORG}=not-int", "invalid RPM"),
    ],
)
def test_parse_org_rpm_overrides_rejects_bad(raw: str, match: str) -> None:
    with pytest.raises(ValueError, match=match):
        parse_org_rpm_overrides(raw)


def test_lua_and_ttl_mirror_go_semantics() -> None:
    assert "INCR" in INCR_EXPIRE_LUA
    assert "EXPIRE" in INCR_EXPIRE_LUA
    assert "n == 1" in INCR_EXPIRE_LUA
    assert KEY_TTL_SECONDS == 90


def test_redis_key_uses_operator_segment() -> None:
    key = RedisOperatorLimiter.redis_key(ORG, unix_minute=12345)
    assert key == f"ratelimit:{ORG}:mcp_operator:12345"


@pytest.mark.asyncio
async def test_noop_always_allows() -> None:
    limiter = NoopOperatorLimiter(default_rpm=5)
    for _ in range(10):
        assert (await limiter.check(ORG)).allowed is True


@pytest.mark.asyncio
async def test_redis_limiter_rejects_over_limit() -> None:
    script = AsyncMock(side_effect=[1, 2, 3])
    redis = MagicMock()
    redis.register_script.return_value = script
    limiter = RedisOperatorLimiter(redis, default_rpm=2, owned=False)

    assert (await limiter.check(ORG)).allowed is True
    assert (await limiter.check(ORG)).allowed is True
    third = await limiter.check(ORG)
    assert third.allowed is False
    assert third.remaining == 0
    assert script.await_args_list[0].kwargs["args"] == [KEY_TTL_SECONDS]


@pytest.mark.asyncio
async def test_redis_limiter_org_override() -> None:
    script = AsyncMock(side_effect=[1, 2])
    redis = MagicMock()
    redis.register_script.return_value = script
    limiter = RedisOperatorLimiter(redis, default_rpm=100, org_overrides={ORG: 1}, owned=False)
    assert (await limiter.check(ORG)).allowed is True
    assert (await limiter.check(ORG)).allowed is False


@pytest.mark.asyncio
async def test_redis_limiter_fail_open_by_default() -> None:
    script = AsyncMock(side_effect=RedisError("down"))
    redis = MagicMock()
    redis.register_script.return_value = script
    limiter = RedisOperatorLimiter(redis, default_rpm=1, owned=False)
    assert (await limiter.check(ORG)).allowed is True


@pytest.mark.asyncio
async def test_redis_limiter_fail_closed_when_configured() -> None:
    script = AsyncMock(side_effect=RedisError("down"))
    redis = MagicMock()
    redis.register_script.return_value = script
    limiter = RedisOperatorLimiter(redis, default_rpm=1, owned=False, fail_closed=True)
    with pytest.raises(RateLimitUnavailableError):
        await limiter.check(ORG)


def test_build_noop_when_redis_unset() -> None:
    limiter = build_operator_rate_limiter(redis_url="", default_rpm=120, org_overrides={})
    assert isinstance(limiter, NoopOperatorLimiter)


@pytest.mark.asyncio
async def test_build_redis_when_url_set() -> None:
    limiter = build_operator_rate_limiter(
        redis_url="redis://127.0.0.1:9/0",
        default_rpm=10,
        org_overrides={uuid4(): 3},
    )
    assert isinstance(limiter, RedisOperatorLimiter)
    await limiter.aclose()


@pytest.mark.asyncio
async def test_abc_check_raises_not_implemented() -> None:
    class _Stub(OperatorRateLimiter):
        async def check(self, org_id: UUID):
            return await OperatorRateLimiter.check(self, org_id)

    limiter = _Stub()
    with pytest.raises(NotImplementedError):
        await limiter.check(ORG)
