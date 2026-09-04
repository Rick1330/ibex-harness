"""Extra edge-case coverage for retrieval clients (cov gate ≥95%)."""

from __future__ import annotations

import json
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
    _hit_from_item,
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
    lookup = RedisDirectiveLookup(redis)
    org_id = uuid4()
    agent_id = uuid4()
    with pytest.raises(DirectiveLookupError):
        await lookup.lookup(org_id, agent_id)


@pytest.mark.asyncio
async def test_redis_directive_invalid_json() -> None:
    redis = AsyncMock()
    redis.get = AsyncMock(return_value=b"not-json")
    lookup = RedisDirectiveLookup(redis)
    org_id = uuid4()
    agent_id = uuid4()
    with pytest.raises(DirectiveLookupError):
        await lookup.lookup(org_id, agent_id)


@pytest.mark.asyncio
async def test_redis_directive_non_object() -> None:
    redis = AsyncMock()
    redis.get = AsyncMock(return_value=b'["not","object"]')
    lookup = RedisDirectiveLookup(redis)
    org_id = uuid4()
    agent_id = uuid4()
    with pytest.raises(DirectiveLookupError):
        await lookup.lookup(org_id, agent_id)


@pytest.mark.asyncio
async def test_redis_directive_default_injection_mode() -> None:
    redis = AsyncMock()
    redis.get = AsyncMock(return_value=b'{"v":1,"content":"x","injection_mode":""}')
    got = await RedisDirectiveLookup(redis).lookup(uuid4(), uuid4())
    assert got.injection_mode == "system_first"


def test_parse_timeout_seconds_suffix() -> None:
    assert _parse_timeout_ms("1s") == 1000.0
    assert _parse_timeout_ms(45) == 45.0


def test_memory_http_client_requires_base_url() -> None:
    with pytest.raises(ValueError):
        MemoryHttpClient(MemoryHttpConfig(base_url="", token="t"))


def test_memory_http_client_requires_token() -> None:
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
            json={"data": {"results": ["bad"]}},
        ),
        "/badrank/v1/memories/hot": httpx.Response(
            200,
            json={
                "data": {
                    "results": [
                        {
                            "memory": {
                                "id": str(uuid4()),
                                "org_id": str(uuid4()),
                                "agent_id": str(uuid4()),
                                "content": "x",
                                "category": "factual",
                                "confidence": 0.5,
                            },
                            "similarity": 0.1,
                            "rank": 0,
                            "source": "hot_cache",
                        }
                    ]
                }
            },
        ),
        "/baduuid/v1/memories/hot": httpx.Response(
            200,
            json={
                "data": {
                    "results": [
                        {
                            "memory": {
                                "id": "not-a-uuid",
                                "org_id": str(uuid4()),
                                "agent_id": str(uuid4()),
                                "content": "x",
                                "category": "factual",
                                "confidence": 0.5,
                            },
                            "similarity": 0.1,
                            "rank": 1,
                            "source": "hot_cache",
                        }
                    ]
                }
            },
        ),
        "/badconf/v1/memories/hot": httpx.Response(
            200,
            json={
                "data": {
                    "results": [
                        {
                            "memory": {
                                "id": str(uuid4()),
                                "org_id": str(uuid4()),
                                "agent_id": str(uuid4()),
                                "content": "x",
                                "category": "factual",
                                "confidence": 1.5,
                            },
                            "similarity": 0.1,
                            "rank": 1,
                            "source": "hot_cache",
                        }
                    ]
                }
            },
        ),
        "/nansim/v1/memories/hot": httpx.Response(
            200,
            content=json.dumps(
                {
                    "data": {
                        "results": [
                            {
                                "memory": {
                                    "id": str(uuid4()),
                                    "org_id": str(uuid4()),
                                    "agent_id": str(uuid4()),
                                    "content": "x",
                                    "category": "factual",
                                    "confidence": 0.5,
                                },
                                "similarity": float("nan"),
                                "rank": 1,
                                "source": "hot_cache",
                            }
                        ]
                    }
                },
                allow_nan=True,
            ).encode(),
            headers={"content-type": "application/json"},
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
    req = HotMemoriesRequest(agent_id=uuid4(), timeout_seconds=0.05)
    with pytest.raises(MemoryHttpError):
        await mem.get_hot_memories(req)


@pytest.mark.asyncio
async def test_memory_http_status_error() -> None:
    transport = httpx.MockTransport(_error_handler)
    async with httpx.AsyncClient(transport=transport) as http:
        await _assert_hot_raises("http://memory.example", http)


@pytest.mark.asyncio
async def test_memory_http_timeout_error() -> None:
    transport = httpx.MockTransport(_error_handler)
    async with httpx.AsyncClient(transport=transport) as http:
        await _assert_hot_raises("http://memory.example/timeout", http)


@pytest.mark.asyncio
async def test_memory_http_transport_error() -> None:
    transport = httpx.MockTransport(_error_handler)
    async with httpx.AsyncClient(transport=transport) as http:
        await _assert_hot_raises("http://memory.example/transport", http)


@pytest.mark.asyncio
async def test_memory_http_malformed_json_bodies() -> None:
    transport = httpx.MockTransport(_error_handler)
    async with httpx.AsyncClient(transport=transport) as http:
        await _assert_hot_raises("http://memory.example/badjson", http)


@pytest.mark.asyncio
async def test_memory_http_missing_data_object() -> None:
    transport = httpx.MockTransport(_error_handler)
    async with httpx.AsyncClient(transport=transport) as http:
        await _assert_hot_raises("http://memory.example/nodata", http)


@pytest.mark.asyncio
async def test_memory_http_missing_results() -> None:
    transport = httpx.MockTransport(_error_handler)
    async with httpx.AsyncClient(transport=transport) as http:
        await _assert_hot_raises("http://memory.example/noresults", http)


@pytest.mark.asyncio
async def test_memory_http_bad_data_type() -> None:
    transport = httpx.MockTransport(_error_handler)
    async with httpx.AsyncClient(transport=transport) as http:
        await _assert_hot_raises("http://memory.example/baddata", http)


@pytest.mark.asyncio
async def test_memory_http_rejects_malformed_result_items() -> None:
    transport = httpx.MockTransport(_error_handler)
    async with httpx.AsyncClient(transport=transport) as http:
        await _assert_hot_raises("http://memory.example/skip", http)


@pytest.mark.asyncio
async def test_memory_http_rejects_invalid_rank() -> None:
    transport = httpx.MockTransport(_error_handler)
    async with httpx.AsyncClient(transport=transport) as http:
        await _assert_hot_raises("http://memory.example/badrank", http)


@pytest.mark.asyncio
async def test_memory_http_rejects_bad_uuid() -> None:
    transport = httpx.MockTransport(_error_handler)
    async with httpx.AsyncClient(transport=transport) as http:
        await _assert_hot_raises("http://memory.example/baduuid", http)


@pytest.mark.asyncio
async def test_memory_http_rejects_confidence_out_of_range() -> None:
    transport = httpx.MockTransport(_error_handler)
    async with httpx.AsyncClient(transport=transport) as http:
        await _assert_hot_raises("http://memory.example/badconf", http)


@pytest.mark.asyncio
async def test_memory_http_rejects_non_finite_similarity() -> None:
    transport = httpx.MockTransport(_error_handler)
    async with httpx.AsyncClient(transport=transport) as http:
        await _assert_hot_raises("http://memory.example/nansim", http)


def test_hit_from_item_rejects_missing_memory() -> None:
    with pytest.raises(MemoryHttpError):
        _hit_from_item({"similarity": 0.1, "rank": 1, "source": "hot_cache"})


def test_hit_from_item_rejects_non_string_fields() -> None:
    mid = str(uuid4())
    with pytest.raises(MemoryHttpError):
        _hit_from_item(
            {
                "memory": {
                    "id": mid,
                    "org_id": mid,
                    "agent_id": mid,
                    "content": 1,
                    "category": "factual",
                    "confidence": 0.5,
                },
                "similarity": 0.1,
                "rank": 1,
                "source": "hot_cache",
            }
        )


def test_hit_from_item_rejects_bool_similarity() -> None:
    mid = str(uuid4())
    with pytest.raises(MemoryHttpError):
        _hit_from_item(
            {
                "memory": {
                    "id": mid,
                    "org_id": mid,
                    "agent_id": mid,
                    "content": "x",
                    "category": "factual",
                    "confidence": 0.5,
                },
                "similarity": True,
                "rank": 1,
                "source": "hot_cache",
            }
        )


def test_hit_from_item_rejects_bool_rank() -> None:
    mid = str(uuid4())
    with pytest.raises(MemoryHttpError):
        _hit_from_item(
            {
                "memory": {
                    "id": mid,
                    "org_id": mid,
                    "agent_id": mid,
                    "content": "x",
                    "category": "factual",
                    "confidence": 0.5,
                },
                "similarity": 0.1,
                "rank": True,
                "source": "hot_cache",
            }
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
