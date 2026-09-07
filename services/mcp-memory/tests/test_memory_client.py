"""Unit coverage for MemoryHttpClient request/response edges."""

from __future__ import annotations

from uuid import UUID, uuid4

import httpx
import pytest

from app.clients.memory import (
    MemoryHttpClient,
    MemoryHttpConfig,
    MemoryHttpError,
    MemoryHttpTimeout,
    build_memory_client,
)
from tests.memory_fixtures import (
    CreatedMemory,
    create_memory_response,
    empty_search_response,
    memory_client_for,
)

ORG = UUID("aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa")
AGENT = UUID("cccccccc-cccc-cccc-cccc-cccccccccccc")


def test_config_rejects_empty_url() -> None:
    config = MemoryHttpConfig(base_url="   ")
    with pytest.raises(ValueError, match="IBEX_MEMORY_HTTP_URL"):
        MemoryHttpClient(config)


def test_config_rejects_non_positive_timeout() -> None:
    config = MemoryHttpConfig(base_url="http://m", timeout_seconds=0)
    with pytest.raises(ValueError, match="timeout"):
        MemoryHttpClient(config)


@pytest.mark.asyncio
async def test_owned_client_aclose() -> None:
    client = build_memory_client(base_url="http://memory.test", timeout_seconds=1.0)
    assert client.base_url == "http://memory.test"
    assert client.timeout_seconds == 1.0
    await client.aclose()


@pytest.mark.asyncio
async def test_missing_token_rejected() -> None:
    client = memory_client_for(lambda _r: empty_search_response())
    with pytest.raises(MemoryHttpError, match="missing bearer"):
        await client.search_memories(token="  ", agent_id=AGENT, query="q", limit=1)


@pytest.mark.asyncio
async def test_transport_error() -> None:
    def handler(_request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("down")

    client = memory_client_for(handler)
    with pytest.raises(MemoryHttpError, match="transport"):
        await client.search_memories(token="t", agent_id=AGENT, query="q", limit=1)


@pytest.mark.asyncio
async def test_timeout_error() -> None:
    def handler(_request: httpx.Request) -> httpx.Response:
        raise httpx.ReadTimeout("slow")

    client = memory_client_for(handler)
    with pytest.raises(MemoryHttpTimeout):
        await client.search_memories(token="t", agent_id=AGENT, query="q", limit=1)


@pytest.mark.asyncio
async def test_invalid_json_body() -> None:
    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, content=b"not-json", headers={"content-type": "text/plain"})

    client = memory_client_for(handler)
    with pytest.raises(MemoryHttpError, match="invalid JSON"):
        await client.search_memories(token="t", agent_id=AGENT, query="q", limit=1)


@pytest.mark.asyncio
async def test_non_object_json() -> None:
    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=[1, 2])

    client = memory_client_for(handler)
    with pytest.raises(MemoryHttpError, match="non-object"):
        await client.search_memories(token="t", agent_id=AGENT, query="q", limit=1)


@pytest.mark.asyncio
async def test_missing_data_object() -> None:
    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"data": "x"})

    client = memory_client_for(handler)
    with pytest.raises(MemoryHttpError, match="missing data"):
        await client.search_memories(token="t", agent_id=AGENT, query="q", limit=1)


@pytest.mark.asyncio
async def test_search_invalid_row_shape() -> None:
    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"data": {"results": [{"similarity": 1}]}})

    client = memory_client_for(handler)
    with pytest.raises(MemoryHttpError, match="search response invalid"):
        await client.search_memories(token="t", agent_id=AGENT, query="q", limit=1)


@pytest.mark.asyncio
async def test_create_invalid_body() -> None:
    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(201, json={"data": {"id": "not-a-uuid"}})

    client = memory_client_for(handler)
    with pytest.raises(MemoryHttpError, match="create response invalid"):
        await client.create_memory(token="t", payload={"agent_id": str(AGENT)}, idempotency_key="k")


@pytest.mark.asyncio
async def test_create_success_parses_metadata_default() -> None:
    mid = str(uuid4())

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.headers["X-Idempotency-Key"] == "abc"
        return create_memory_response(
            CreatedMemory(memory_id=mid, org_id=ORG, agent_id=AGENT, metadata={})
        )

    client = memory_client_for(handler)
    result = await client.create_memory(
        token="tok",
        payload={"agent_id": str(AGENT), "content": "c"},
        idempotency_key="abc",
    )
    assert result.memory_id == mid
    assert result.metadata == {}
    assert result.org_id == str(ORG)
