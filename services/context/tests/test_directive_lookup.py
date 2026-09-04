"""Unit tests for Redis directive envelope lookup."""

from __future__ import annotations

import json
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest

from app.clients.directive import DirectiveLookupError, RedisDirectiveLookup


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
    with pytest.raises(DirectiveLookupError):
        await RedisDirectiveLookup(redis).lookup(uuid4(), uuid4())


@pytest.mark.asyncio
async def test_config_parses_timeout_ms_suffix() -> None:
    from app.config import ContextSettings

    settings = ContextSettings.model_validate({"IBEX_CONTEXT_TIMEOUT": "45ms"})
    assert settings.timeout_ms == 45.0
