"""Extra edge-case coverage for retrieval clients (cov gate ≥95%)."""

from __future__ import annotations

from unittest.mock import AsyncMock
from uuid import uuid4

import httpx
import pytest
from redis.exceptions import RedisError

from app.clients.directive import (
    DirectiveLookupError,
    EmptyDirectiveLookup,
    RedisDirectiveLookup,
)
from app.clients.memory import (
    HotMemoriesRequest,
    MemoryHttpClient,
    MemoryHttpConfig,
    MemoryHttpError,
)
from app.config import _parse_timeout_ms
from app.retrieval import (
    BranchOutcome,
    ParallelRetriever,
    _BranchResult,
    _coerce_branch,
)
from tests.test_retrieval import _request, _settings, _StubMemory


@pytest.mark.asyncio
async def test_empty_directive_lookup() -> None:
    got = await EmptyDirectiveLookup().lookup(uuid4(), uuid4())
    assert got.content == ""


@pytest.mark.asyncio
async def test_redis_directive_redis_error() -> None:
    redis = AsyncMock()
    redis.get = AsyncMock(side_effect=RedisError("down"))
    with pytest.raises(DirectiveLookupError):
        await RedisDirectiveLookup(redis).lookup(uuid4(), uuid4())


@pytest.mark.asyncio
async def test_redis_directive_invalid_json() -> None:
    redis = AsyncMock()
    redis.get = AsyncMock(return_value=b"not-json")
    with pytest.raises(DirectiveLookupError):
        await RedisDirectiveLookup(redis).lookup(uuid4(), uuid4())


@pytest.mark.asyncio
async def test_redis_directive_non_object() -> None:
    redis = AsyncMock()
    redis.get = AsyncMock(return_value=b'["not","object"]')
    with pytest.raises(DirectiveLookupError):
        await RedisDirectiveLookup(redis).lookup(uuid4(), uuid4())


@pytest.mark.asyncio
async def test_redis_directive_default_injection_mode() -> None:
    redis = AsyncMock()
    redis.get = AsyncMock(return_value=b'{"v":1,"content":"x","injection_mode":""}')
    got = await RedisDirectiveLookup(redis).lookup(uuid4(), uuid4())
    assert got.injection_mode == "system_first"


def test_parse_timeout_seconds_suffix() -> None:
    assert _parse_timeout_ms("1s") == 1000.0
    assert _parse_timeout_ms(45) == 45.0


def test_memory_http_client_requires_config() -> None:
    with pytest.raises(ValueError):
        MemoryHttpClient(MemoryHttpConfig(base_url="", token="t"))
    with pytest.raises(ValueError):
        MemoryHttpClient(MemoryHttpConfig(base_url="http://x", token=""))


def _error_handler(request: httpx.Request) -> httpx.Response:
    path = request.url.path
    responses: dict[str, httpx.Response | Exception] = {
        "/timeout/v1/memories/hot": httpx.ReadTimeout("slow"),
        "/transport/v1/memories/hot": httpx.ConnectError("nope"),
        "/badjson/v1/memories/hot": httpx.Response(200, content=b"not-json"),
        "/nodata/v1/memories/hot": httpx.Response(200, json=["x"]),
        "/noresults/v1/memories/hot": httpx.Response(200, json={"data": {}}),
        "/baddata/v1/memories/hot": httpx.Response(200, json={"data": "x"}),
        "/skip/v1/memories/hot": httpx.Response(
            200,
            json={"data": {"results": ["bad", {"similarity": 1}, {"memory": "x"}]}},
        ),
    }
    for suffix, value in responses.items():
        if path.endswith(suffix):
            if isinstance(value, Exception):
                raise value
            return value
    return httpx.Response(503, json={"detail": "down"})


async def _assert_hot_raises(base: str, http: httpx.AsyncClient) -> None:
    mem = MemoryHttpClient(MemoryHttpConfig(base_url=base, token="t"), client=http)
    with pytest.raises(MemoryHttpError):
        await mem.get_hot_memories(
            HotMemoriesRequest(agent_id=uuid4(), timeout_seconds=0.05)
        )


@pytest.mark.asyncio
async def test_memory_http_status_and_transport_errors() -> None:
    transport = httpx.MockTransport(_error_handler)
    async with httpx.AsyncClient(transport=transport) as http:
        await _assert_hot_raises("http://memory.example", http)
        await _assert_hot_raises("http://memory.example/timeout", http)
        await _assert_hot_raises("http://memory.example/transport", http)


@pytest.mark.asyncio
async def test_memory_http_malformed_json_bodies() -> None:
    transport = httpx.MockTransport(_error_handler)
    async with httpx.AsyncClient(transport=transport) as http:
        await _assert_hot_raises("http://memory.example/badjson", http)
        await _assert_hot_raises("http://memory.example/nodata", http)
        await _assert_hot_raises("http://memory.example/noresults", http)
        await _assert_hot_raises("http://memory.example/baddata", http)


@pytest.mark.asyncio
async def test_memory_http_skips_malformed_result_items() -> None:
    transport = httpx.MockTransport(_error_handler)
    async with httpx.AsyncClient(transport=transport) as http:
        mem = MemoryHttpClient(
            MemoryHttpConfig(base_url="http://memory.example/skip", token="t"),
            client=http,
        )
        assert (
            await mem.get_hot_memories(
                HotMemoriesRequest(agent_id=uuid4(), timeout_seconds=0.05)
            )
            == []
        )


@pytest.mark.asyncio
async def test_memory_http_owns_client_aclose() -> None:
    mem = MemoryHttpClient(MemoryHttpConfig(base_url="http://memory.example", token="t"))
    await mem.aclose()


@pytest.mark.asyncio
async def test_retrieval_generic_exceptions_and_coerce() -> None:
    class BoomDirective:
        async def lookup(self, org_id, agent_id):
            raise RuntimeError("unexpected")

    memory = _StubMemory(hot=RuntimeError("hot boom"), cold=RuntimeError("cold boom"))
    result = await ParallelRetriever(
        settings=_settings(),
        memory=memory,  # type: ignore[arg-type]
        directive=BoomDirective(),
    ).retrieve(_request())
    assert result.directive_outcome.status == "error"
    assert result.hot_outcome.status == "error"
    assert result.cold_outcome.status == "error"

    assert _coerce_branch("hot", RuntimeError("x")).outcome.status == "error"
    assert _coerce_branch("cold", "weird").outcome.status == "error"
    ok = _BranchResult(name="directive", outcome=BranchOutcome("success", 1.0))
    assert _coerce_branch("directive", ok) is ok
