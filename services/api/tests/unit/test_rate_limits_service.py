"""Service + Redis publisher unit tests for rate-limit config (m4.B.2)."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest
from apierror_py import NOT_FOUND, VALIDATION_ERROR

from app.errors import ApiError
from app.rate_limit_publish import (
    NoopRateLimitConfigPublisher,
    RecordingRateLimitConfigPublisher,
    RedisRateLimitConfigPublisher,
    RedisRateLimitCounter,
)
from app.schemas.rate_limits import RateLimitsPatchRequest
from app.services import rate_limits as rate_limit_service


def _patch_deps(**kwargs):
    return rate_limit_service.PatchDeps(
        platform_default_rpm=60,
        counter=kwargs.get("counter", AsyncMock()),
        publisher=kwargs.get("publisher", NoopRateLimitConfigPublisher()),
    )


async def _expect_patch_error(session, org_id, body, deps, code: str) -> None:
    coro = rate_limit_service.patch_rate_limits(session, org_id, body, deps=deps)
    with pytest.raises(ApiError) as exc:
        await coro
    assert exc.value.code == code


@pytest.mark.asyncio
async def test_get_rate_limits_service_maps_rows() -> None:
    org_id = uuid4()
    agent_id = uuid4()

    class _Rows:
        def all(self):
            return [(None, 150), (agent_id, 30)]

    session = AsyncMock()
    session.execute = AsyncMock(return_value=_Rows())
    counter = AsyncMock()
    counter.org_current_minute_requests = AsyncMock(return_value=7)
    got = await rate_limit_service.get_rate_limits(
        session, org_id, platform_default_rpm=60, counter=counter
    )
    assert got.requests_per_minute == 150
    assert got.source == "override"
    assert got.current_minute_requests == 7
    assert len(got.agent_overrides) == 1
    assert got.agent_overrides[0].requests_per_minute == 30


@pytest.mark.asyncio
async def test_patch_rate_limits_publish_failure_does_not_raise() -> None:
    org_id = uuid4()
    session = AsyncMock()
    session.execute = AsyncMock(
        side_effect=[
            MagicMock(),
            MagicMock(all=lambda: [(None, 80)]),
        ]
    )
    session.flush = AsyncMock()
    session.commit = AsyncMock()

    class _Boom:
        async def publish_config_update(self, _org_id: str) -> None:
            raise RuntimeError("redis down")

    counter = AsyncMock()
    counter.org_current_minute_requests = AsyncMock(return_value=0)
    got = await rate_limit_service.patch_rate_limits(
        session,
        org_id,
        RateLimitsPatchRequest(requests_per_minute=80),
        deps=_patch_deps(counter=counter, publisher=_Boom()),
    )
    assert got.requests_per_minute == 80
    session.commit.assert_awaited()


@pytest.mark.asyncio
async def test_patch_clear_org_and_agent_validation() -> None:
    await _expect_patch_error(
        AsyncMock(),
        uuid4(),
        RateLimitsPatchRequest(requests_per_minute=10, clear_org_override=True),
        _patch_deps(),
        VALIDATION_ERROR,
    )


@pytest.mark.asyncio
async def test_patch_unknown_agent_404() -> None:
    class _ScalarNone:
        def scalar_one_or_none(self):
            return None

    session = AsyncMock()
    session.execute = AsyncMock(return_value=_ScalarNone())
    await _expect_patch_error(
        session,
        uuid4(),
        RateLimitsPatchRequest(
            agent_overrides=[{"agent_id": uuid4(), "requests_per_minute": 5}]
        ),
        _patch_deps(),
        NOT_FOUND,
    )


@pytest.mark.asyncio
async def test_patch_agent_upsert_and_clear() -> None:
    org_id = uuid4()
    agent_id = uuid4()

    class _ScalarOK:
        def scalar_one_or_none(self):
            return 1

    class _Rows:
        def all(self):
            return []

    session = AsyncMock()
    session.execute = AsyncMock(
        side_effect=[
            _ScalarOK(),
            MagicMock(),
            _Rows(),
            MagicMock(),
            _ScalarOK(),
            MagicMock(),
            _Rows(),
        ]
    )
    session.flush = AsyncMock()
    session.commit = AsyncMock()
    counter = AsyncMock()
    counter.org_current_minute_requests = AsyncMock(return_value=0)
    pub = RecordingRateLimitConfigPublisher()
    deps = _patch_deps(counter=counter, publisher=pub)
    await rate_limit_service.patch_rate_limits(
        session,
        org_id,
        RateLimitsPatchRequest(
            agent_overrides=[{"agent_id": agent_id, "requests_per_minute": 11}]
        ),
        deps=deps,
    )
    await rate_limit_service.patch_rate_limits(
        session,
        org_id,
        RateLimitsPatchRequest(
            agent_overrides=[{"agent_id": agent_id, "requests_per_minute": None}],
            clear_org_override=True,
        ),
        deps=deps,
    )
    assert pub.published == [str(org_id), str(org_id)]


class _FakeRedis:
    def __init__(self, *, get_impl=None, publish_impl=None) -> None:
        self._get = get_impl
        self._publish = publish_impl
        self.published: list[tuple[str, str]] = []

    async def get(self, key):
        if self._get is None:
            return None
        return await self._get(key)

    async def publish(self, channel, payload):
        self.published.append((channel, payload))
        if self._publish is not None:
            await self._publish(channel, payload)

    async def aclose(self):
        return None


@pytest.mark.asyncio
async def test_counter_get_errors_and_bad_values() -> None:
    async def boom(_key):
        raise RuntimeError("boom")

    counter = RedisRateLimitCounter("redis://x")
    counter._client = _FakeRedis(get_impl=boom)  # type: ignore[assignment]
    assert await counter.org_current_minute_requests("o") == 0

    async def bad(_key):
        return "x"

    counter2 = RedisRateLimitCounter("redis://x")
    counter2._client = _FakeRedis(get_impl=bad)  # type: ignore[assignment]
    assert await counter2.org_current_minute_requests("o") == 0


@pytest.mark.asyncio
async def test_noop_and_recording_publishers() -> None:
    await NoopRateLimitConfigPublisher().publish_config_update("x")
    rec = RecordingRateLimitConfigPublisher()
    await rec.publish_config_update("y")
    assert rec.published == ["y"]

    async def get_rpm(key):
        if key.endswith(":rpm:1"):
            return "9"
        return None

    fake = _FakeRedis(get_impl=get_rpm)
    pub = RedisRateLimitConfigPublisher("redis://localhost:6379/0")
    pub._client = fake  # type: ignore[assignment]
    await pub.publish_config_update("550e8400-e29b-41d4-a716-446655440001")
    assert fake.published[0][0].startswith("ratelimit_config_updates:")
    payload = fake.published[0][1].replace(" ", "")
    assert '"v":1' in payload

    counter = RedisRateLimitCounter("redis://localhost:6379/0")
    counter._client = fake  # type: ignore[assignment]
    with patch("time.time", return_value=60):
        assert await counter.org_current_minute_requests("org") == 9
    assert await RedisRateLimitCounter(None).org_current_minute_requests("org") == 0
    await pub.aclose()
    await counter.aclose()
