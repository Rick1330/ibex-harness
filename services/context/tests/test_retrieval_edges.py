"""Extra edge-case coverage for retrieval clients (cov gate ≥95%)."""

from __future__ import annotations

import json
from typing import Any
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
    with pytest.raises(DirectiveLookupError):
        await RedisDirectiveLookup(redis).lookup(uuid4(), uuid4())


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "raw",
    [b"not-json", b'["not","object"]'],
)
async def test_redis_directive_parse_failures(raw: bytes) -> None:
    redis = AsyncMock()
    redis.get = AsyncMock(return_value=raw)
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


def test_memory_http_client_requires_base_url() -> None:
    with pytest.raises(ValueError):
        MemoryHttpClient(MemoryHttpConfig(base_url="", token="t"))


def test_memory_http_client_requires_token() -> None:
    with pytest.raises(ValueError):
        MemoryHttpClient(MemoryHttpConfig(base_url="http://x", token=""))


def _memory_fields(**overrides: Any) -> dict[str, Any]:
    mid = str(uuid4())
    base: dict[str, Any] = {
        "id": mid,
        "org_id": mid,
        "agent_id": mid,
        "content": "x",
        "category": "factual",
        "confidence": 0.5,
    }
    base.update(overrides)
    return base


def _result_item(**overrides: Any) -> dict[str, Any]:
    item: dict[str, Any] = {
        "memory": _memory_fields(),
        "similarity": 0.1,
        "rank": 1,
        "source": "hot_cache",
    }
    memory_overrides = overrides.pop("memory", None)
    item.update(overrides)
    if memory_overrides is not None:
        item["memory"] = _memory_fields(**memory_overrides)
    return item


def _results_response(*items: object) -> httpx.Response:
    return httpx.Response(200, json={"data": {"results": list(items)}})


def _nan_similarity_response() -> httpx.Response:
    return httpx.Response(
        200,
        content=json.dumps(
            {"data": {"results": [_result_item(similarity=float("nan"))]}},
            allow_nan=True,
        ).encode(),
        headers={"content-type": "application/json"},
    )


def _error_routes() -> dict[str, httpx.Response | Exception]:
    return {
        "/timeout/v1/memories/hot": httpx.ReadTimeout("slow"),
        "/transport/v1/memories/hot": httpx.ConnectError("nope"),
        "/badjson/v1/memories/hot": httpx.Response(200, content=b"not-json"),
        "/nodata/v1/memories/hot": httpx.Response(200, json=["x"]),
        "/noresults/v1/memories/hot": httpx.Response(200, json={"data": {}}),
        "/baddata/v1/memories/hot": httpx.Response(200, json={"data": "x"}),
        "/skip/v1/memories/hot": _results_response("bad"),
        "/badrank/v1/memories/hot": _results_response(_result_item(rank=0)),
        "/baduuid/v1/memories/hot": _results_response(
            _result_item(memory={"id": "not-a-uuid"})
        ),
        "/badconf/v1/memories/hot": _results_response(
            _result_item(memory={"confidence": 1.5})
        ),
        "/nansim/v1/memories/hot": _nan_similarity_response(),
    }


def _error_handler(request: httpx.Request) -> httpx.Response:
    for suffix, value in _error_routes().items():
        if request.url.path.endswith(suffix):
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
@pytest.mark.parametrize(
    "base",
    [
        "http://memory.example",
        "http://memory.example/timeout",
        "http://memory.example/transport",
        "http://memory.example/badjson",
        "http://memory.example/nodata",
        "http://memory.example/noresults",
        "http://memory.example/baddata",
        "http://memory.example/skip",
        "http://memory.example/badrank",
        "http://memory.example/baduuid",
        "http://memory.example/badconf",
        "http://memory.example/nansim",
    ],
)
async def test_memory_http_error_paths(base: str) -> None:
    transport = httpx.MockTransport(_error_handler)
    async with httpx.AsyncClient(transport=transport) as http:
        await _assert_hot_raises(base, http)


def _valid_hit(**overrides: Any) -> dict[str, Any]:
    return _result_item(**overrides)


@pytest.mark.parametrize(
    "item",
    [
        {"similarity": 0.1, "rank": 1, "source": "hot_cache"},
        _valid_hit(memory={"content": 1}),
        _valid_hit(similarity=True),
        _valid_hit(rank=True),
    ],
)
def test_hit_from_item_rejects_invalid(item: object) -> None:
    with pytest.raises(MemoryHttpError):
        _hit_from_item(item)


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
