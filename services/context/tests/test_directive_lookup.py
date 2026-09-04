"""Unit tests for Redis directive envelope lookup."""

from __future__ import annotations

import json
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest

from app.clients.directive import DirectiveLookupError, RedisDirectiveLookup
from app.config import ContextSettings, _parse_timeout_ms


@pytest.mark.asyncio
async def test_redis_directive_lookup_parses_go_envelope() -> None:
    org_id = uuid4()
    agent_id = uuid4()
    version_id = uuid4()
    redis = AsyncMock()
    redis.get = AsyncMock(
        return_value=json.dumps(
            {
                "v": 1,
                "content": "Be precise.",
                "injection_mode": "system_append",
                "version_id": str(version_id),
            }
        ).encode()
    )
    lookup = RedisDirectiveLookup(redis)
    got = await lookup.lookup(org_id, agent_id)
    redis.get.assert_awaited_once_with(f"{org_id}:directive:{agent_id}")
    assert got.content == "Be precise."
    assert got.injection_mode == "system_append"
    assert got.version_id == str(version_id)


@pytest.mark.asyncio
async def test_redis_directive_lookup_miss_is_empty() -> None:
    redis = AsyncMock()
    redis.get = AsyncMock(return_value=None)
    got = await RedisDirectiveLookup(redis).lookup(uuid4(), uuid4())
    assert got.content == ""


@pytest.mark.asyncio
async def test_redis_directive_lookup_bad_envelope_raises() -> None:
    redis = AsyncMock()
    redis.get = AsyncMock(return_value=b'{"v":99,"content":"x"}')
    lookup = RedisDirectiveLookup(redis)
    org_id = uuid4()
    agent_id = uuid4()
    with pytest.raises(DirectiveLookupError):
        await lookup.lookup(org_id, agent_id)


@pytest.mark.asyncio
async def test_redis_directive_rejects_bad_version_id() -> None:
    redis = AsyncMock()
    redis.get = AsyncMock(
        return_value=b'{"v":1,"content":"x","injection_mode":"system_first","version_id":"not-a-uuid"}'
    )
    lookup = RedisDirectiveLookup(redis)
    org_id = uuid4()
    agent_id = uuid4()
    with pytest.raises(DirectiveLookupError):
        await lookup.lookup(org_id, agent_id)


@pytest.mark.asyncio
async def test_redis_directive_normalizes_unknown_mode() -> None:
    redis = AsyncMock()
    redis.get = AsyncMock(
        return_value=b'{"v":1,"content":"x","injection_mode":"nope"}'
    )
    got = await RedisDirectiveLookup(redis).lookup(uuid4(), uuid4())
    assert got.injection_mode == "system_first"


@pytest.mark.asyncio
async def test_redis_directive_rejects_non_string_content() -> None:
    redis = AsyncMock()
    redis.get = AsyncMock(
        return_value=b'{"v":1,"content":123,"injection_mode":"system_first"}'
    )
    lookup = RedisDirectiveLookup(redis)
    org_id = uuid4()
    agent_id = uuid4()
    with pytest.raises(DirectiveLookupError):
        await lookup.lookup(org_id, agent_id)


@pytest.mark.asyncio
async def test_redis_directive_null_content_and_mode() -> None:
    redis = AsyncMock()
    redis.get = AsyncMock(
        return_value=b'{"v":1,"content":null,"injection_mode":null}'
    )
    got = await RedisDirectiveLookup(redis).lookup(uuid4(), uuid4())
    assert got.content == ""
    assert got.injection_mode == "system_first"


@pytest.mark.asyncio
async def test_redis_directive_rejects_non_string_mode() -> None:
    redis = AsyncMock()
    redis.get = AsyncMock(
        return_value=b'{"v":1,"content":"x","injection_mode":1}'
    )
    lookup = RedisDirectiveLookup(redis)
    org_id = uuid4()
    agent_id = uuid4()
    with pytest.raises(DirectiveLookupError):
        await lookup.lookup(org_id, agent_id)


@pytest.mark.asyncio
async def test_redis_directive_rejects_non_utf8_bytes() -> None:
    redis = AsyncMock()
    redis.get = AsyncMock(return_value=b"\xff\xfe not utf8")
    lookup = RedisDirectiveLookup(redis)
    org_id = uuid4()
    agent_id = uuid4()
    with pytest.raises(DirectiveLookupError):
        await lookup.lookup(org_id, agent_id)


@pytest.mark.asyncio
async def test_redis_directive_rejects_non_string_version_id() -> None:
    redis = AsyncMock()
    redis.get = AsyncMock(
        return_value=b'{"v":1,"content":"x","injection_mode":"system_first","version_id":123}'
    )
    lookup = RedisDirectiveLookup(redis)
    org_id = uuid4()
    agent_id = uuid4()
    with pytest.raises(DirectiveLookupError):
        await lookup.lookup(org_id, agent_id)


def test_config_parses_timeout_ms_suffix() -> None:
    settings = ContextSettings.model_validate({"IBEX_CONTEXT_TIMEOUT": "45ms"})
    assert settings.timeout_ms == 45.0


@pytest.mark.parametrize("value", [float("inf"), float("-inf"), float("nan"), "nan", "inf"])
def test_parse_timeout_rejects_non_finite(value: object) -> None:
    with pytest.raises(ValueError):
        _parse_timeout_ms(value)


def test_parse_timeout_rejects_bool() -> None:
    with pytest.raises(TypeError):
        _parse_timeout_ms(True)
