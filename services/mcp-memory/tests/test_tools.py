"""Tool schema, agent resolution, and memory-HTTP handler tests."""

from __future__ import annotations

import json
from uuid import UUID, uuid4

import httpx
import pytest

from app.access_token import set_access_token
from app.clients.memory import MemoryHttpClient, MemoryHttpConfig
from app.errors import PermissionDeniedError, SchemaError
from app.permissions import MEMORY_READ, MEMORY_WRITE
from app.principal import Principal
from app.tools import (
    SEARCH_MEMORY_SCHEMA,
    WRITE_MEMORY_SCHEMA,
    parse_search_args,
    parse_write_args,
    resolve_tool_agent_id,
    search_memory,
    write_idempotency_key,
    write_memory,
)

ORG_A = UUID("aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa")
ORG_B = UUID("bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb")
AGENT = UUID("cccccccc-cccc-cccc-cccc-cccccccccccc")
AGENT_OTHER = UUID("dddddddd-dddd-dddd-dddd-dddddddddddd")
TOKEN = "tok-test"


def _client(handler) -> MemoryHttpClient:
    return MemoryHttpClient(
        MemoryHttpConfig(base_url="http://memory.test", timeout_seconds=1.0),
        client=httpx.AsyncClient(transport=httpx.MockTransport(handler)),
    )


def test_search_schema_rejects_extra() -> None:
    with pytest.raises(SchemaError):
        parse_search_args({"query": "x", "extra": 1})


def test_write_schema_rejects_bad_category() -> None:
    with pytest.raises(SchemaError):
        parse_write_args({"content": "hello", "category": "fact"})


def test_write_schema_accepts_memory_api_categories() -> None:
    args = parse_write_args({"content": "hello", "category": "episodic"})
    assert args.category == "episodic"


def test_schemas_forbid_additional_properties() -> None:
    assert SEARCH_MEMORY_SCHEMA["additionalProperties"] is False
    assert WRITE_MEMORY_SCHEMA["additionalProperties"] is False
    assert set(WRITE_MEMORY_SCHEMA["properties"]["category"]["enum"]) == {
        "factual",
        "preference",
        "behavioral",
        "episodic",
        "procedural",
    }


def test_resolve_agent_prefers_principal() -> None:
    principal = Principal(org_id=ORG_A, permissions=MEMORY_READ, agent_id=AGENT)
    assert resolve_tool_agent_id(principal, AGENT) == AGENT
    assert resolve_tool_agent_id(principal, None) == AGENT


def test_resolve_agent_mismatch_denied() -> None:
    principal = Principal(org_id=ORG_A, permissions=MEMORY_READ, agent_id=AGENT)
    with pytest.raises(PermissionDeniedError):
        resolve_tool_agent_id(principal, AGENT_OTHER)


def test_resolve_agent_from_arg() -> None:
    principal = Principal(org_id=ORG_A, permissions=MEMORY_READ)
    assert resolve_tool_agent_id(principal, AGENT) == AGENT


def test_resolve_agent_missing_rejected() -> None:
    principal = Principal(org_id=ORG_A, permissions=MEMORY_READ)
    with pytest.raises(SchemaError, match="agent_id"):
        resolve_tool_agent_id(principal, None)


def test_idempotency_key_stable() -> None:
    a = write_idempotency_key(org_id=ORG_A, agent_id=AGENT, content="  Hello\u0041  ")
    b = write_idempotency_key(org_id=ORG_A, agent_id=AGENT, content="HelloA")
    # NFC+strip: "HelloA" vs "  HelloA  " after NFC of Hello\u0041
    c = write_idempotency_key(org_id=ORG_A, agent_id=AGENT, content="HelloA")
    assert a == c
    assert b == c
    d = write_idempotency_key(org_id=ORG_B, agent_id=AGENT, content="HelloA")
    assert d != c


@pytest.mark.asyncio
async def test_search_requires_memory_read() -> None:
    principal = Principal(org_id=ORG_A, permissions=0, agent_id=AGENT)
    args = parse_search_args({"query": "q"})
    calls = {"n": 0}

    def handler(_request: httpx.Request) -> httpx.Response:
        calls["n"] += 1
        return httpx.Response(200, json={"data": {"results": []}})

    with pytest.raises(PermissionDeniedError):
        await search_memory(principal, args, _client(handler))
    assert calls["n"] == 0


@pytest.mark.asyncio
async def test_write_requires_memory_write() -> None:
    principal = Principal(org_id=ORG_A, permissions=MEMORY_READ, agent_id=AGENT)
    args = parse_write_args({"content": "c"})
    calls = {"n": 0}

    def handler(_request: httpx.Request) -> httpx.Response:
        calls["n"] += 1
        return httpx.Response(201, json={"data": {}})

    with pytest.raises(PermissionDeniedError):
        await write_memory(principal, args, _client(handler))
    assert calls["n"] == 0


@pytest.mark.asyncio
async def test_search_success_with_hits() -> None:
    mid = str(uuid4())

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.headers["Authorization"] == f"Bearer {TOKEN}"
        body = json.loads(request.content)
        assert body["agent_id"] == str(AGENT)
        assert body["query"] == "theme"
        return httpx.Response(
            200,
            json={
                "data": {
                    "results": [
                        {
                            "memory": {
                                "id": mid,
                                "agent_id": str(AGENT),
                                "org_id": str(ORG_A),
                                "content": "hit",
                                "category": "preference",
                                "confidence": 0.9,
                                "status": "active",
                                "created_at": "2026-01-01T00:00:00Z",
                                "updated_at": "2026-01-01T00:00:00Z",
                            },
                            "similarity": 0.88,
                            "rank": 1,
                            "source": "vector",
                        }
                    ]
                }
            },
        )

    set_access_token(TOKEN)
    try:
        out = await search_memory(
            Principal(org_id=ORG_A, permissions=MEMORY_READ, agent_id=AGENT),
            parse_search_args({"query": "theme", "limit": 5}),
            _client(handler),
        )
    finally:
        set_access_token(None)
    assert out["results"][0]["memory_id"] == mid
    assert out["results"][0]["score"] == 0.88
    assert out["org_id"] == str(ORG_A)


@pytest.mark.asyncio
async def test_search_empty_hits_is_success() -> None:
    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"data": {"results": []}})

    set_access_token(TOKEN)
    try:
        out = await search_memory(
            Principal(org_id=ORG_A, permissions=MEMORY_READ, agent_id=AGENT),
            parse_search_args({"query": "none"}),
            _client(handler),
        )
    finally:
        set_access_token(None)
    assert out["results"] == []


@pytest.mark.asyncio
async def test_search_backend_503_fail_closed() -> None:
    from app.errors import BackendUnavailableError

    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(503, text="busy")

    set_access_token(TOKEN)
    try:
        with pytest.raises(BackendUnavailableError):
            await search_memory(
                Principal(org_id=ORG_A, permissions=MEMORY_READ, agent_id=AGENT),
                parse_search_args({"query": "q"}),
                _client(handler),
            )
    finally:
        set_access_token(None)


@pytest.mark.asyncio
async def test_search_timeout_fail_closed() -> None:
    from app.errors import BackendUnavailableError

    def handler(_request: httpx.Request) -> httpx.Response:
        raise httpx.ReadTimeout("slow")

    set_access_token(TOKEN)
    try:
        with pytest.raises(BackendUnavailableError):
            await search_memory(
                Principal(org_id=ORG_A, permissions=MEMORY_READ, agent_id=AGENT),
                parse_search_args({"query": "q"}),
                _client(handler),
            )
    finally:
        set_access_token(None)


@pytest.mark.asyncio
async def test_search_403_is_permission_denied() -> None:
    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(403, json={"detail": {"code": "AGENT_NOT_AUTHORIZED"}})

    set_access_token(TOKEN)
    try:
        with pytest.raises(PermissionDeniedError):
            await search_memory(
                Principal(org_id=ORG_A, permissions=MEMORY_READ, agent_id=AGENT),
                parse_search_args({"query": "q"}),
                _client(handler),
            )
    finally:
        set_access_token(None)


@pytest.mark.asyncio
async def test_write_success_mcp_source_metadata_and_idempotency() -> None:
    mid = str(uuid4())
    seen_keys: list[str] = []
    bodies: list[dict] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen_keys.append(request.headers["X-Idempotency-Key"])
        bodies.append(json.loads(request.content))
        return httpx.Response(
            201,
            json={
                "data": {
                    "id": mid,
                    "agent_id": str(AGENT),
                    "org_id": str(ORG_A),
                    "content": "remember",
                    "content_tokens": 1,
                    "category": "factual",
                    "confidence": 0.6,
                    "source": "user_provided",
                    "status": "active",
                    "visibility": "agent",
                    "pinned": False,
                    "tags": [],
                    "retrieval_count": 0,
                    "usefulness_score": 0.5,
                    "pii_detected": False,
                    "metadata": {"mcp_source": "mcp_explicit"},
                    "created_at": "2026-01-01T00:00:00Z",
                    "updated_at": "2026-01-01T00:00:00Z",
                },
                "meta": {"deduplication": {"is_duplicate": False}, "processing_time_ms": 1},
            },
        )

    set_access_token(TOKEN)
    try:
        principal = Principal(org_id=ORG_A, permissions=MEMORY_WRITE, agent_id=AGENT)
        args = parse_write_args({"content": "remember", "category": "factual"})
        client = _client(handler)
        first = await write_memory(principal, args, client)
        second = await write_memory(principal, args, client)
    finally:
        set_access_token(None)

    assert first["memory_id"] == mid
    assert first["persisted"] is True
    assert first["mcp_source"] == "mcp_explicit"
    assert first["source"] == "user_provided"
    assert bodies[0]["metadata"] == {"mcp_source": "mcp_explicit"}
    assert "source" not in bodies[0]
    assert seen_keys[0] == seen_keys[1]
    assert seen_keys[0] == write_idempotency_key(
        org_id=ORG_A, agent_id=AGENT, content="remember"
    )
    assert second["memory_id"] == mid
