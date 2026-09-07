"""Tool schema, agent resolution, and memory-HTTP handler tests."""

from __future__ import annotations

import json
from uuid import UUID, uuid4

import httpx
import pytest

from app.access_token import get_access_token, require_access_token, set_access_token
from app.errors import (
    AuthFailedError,
    BackendRejectedError,
    BackendUnavailableError,
    PermissionDeniedError,
    SchemaError,
)
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
from tests.memory_fixtures import create_memory_response, memory_client_for

ORG_A = UUID("aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa")
ORG_B = UUID("bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb")
AGENT = UUID("cccccccc-cccc-cccc-cccc-cccccccccccc")
AGENT_OTHER = UUID("dddddddd-dddd-dddd-dddd-dddddddddddd")
TOKEN = "tok-test"


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
    c = write_idempotency_key(org_id=ORG_A, agent_id=AGENT, content="HelloA")
    assert a == c
    assert b == c
    d = write_idempotency_key(org_id=ORG_B, agent_id=AGENT, content="HelloA")
    assert d != c


def test_access_token_require_and_get() -> None:
    set_access_token(None)
    assert get_access_token() is None
    with pytest.raises(AuthFailedError):
        require_access_token()
    set_access_token("   ")
    with pytest.raises(AuthFailedError):
        require_access_token()
    set_access_token(TOKEN)
    assert require_access_token() == TOKEN
    assert get_access_token() == TOKEN
    set_access_token(None)


def test_backend_rejected_default_code() -> None:
    err = BackendRejectedError("nope")
    assert err.code == "backend_error"


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("tool", "permissions", "args"),
    [
        ("search", 0, {"query": "q"}),
        ("write", MEMORY_READ, {"content": "c"}),
    ],
)
async def test_permission_denied_skips_http(
    tool: str, permissions: int, args: dict
) -> None:
    principal = Principal(org_id=ORG_A, permissions=permissions, agent_id=AGENT)
    calls = {"n": 0}

    def handler(_request: httpx.Request) -> httpx.Response:
        calls["n"] += 1
        return httpx.Response(200, json={"data": {"results": []}})

    client = memory_client_for(handler)
    with pytest.raises(PermissionDeniedError):
        if tool == "search":
            await search_memory(principal, parse_search_args(args), client)
        else:
            await write_memory(principal, parse_write_args(args), client)
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
            memory_client_for(handler),
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
            memory_client_for(handler),
        )
    finally:
        set_access_token(None)
    assert out["results"] == []


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("status", "exc_type"),
    [
        (503, BackendUnavailableError),
        (403, PermissionDeniedError),
        (401, PermissionDeniedError),
        (409, BackendRejectedError),
    ],
)
async def test_search_http_errors_fail_closed(status: int, exc_type: type) -> None:
    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(status, text="err")

    set_access_token(TOKEN)
    try:
        with pytest.raises(exc_type):
            await search_memory(
                Principal(org_id=ORG_A, permissions=MEMORY_READ, agent_id=AGENT),
                parse_search_args({"query": "q"}),
                memory_client_for(handler),
            )
    finally:
        set_access_token(None)


@pytest.mark.asyncio
async def test_search_timeout_fail_closed() -> None:
    def handler(_request: httpx.Request) -> httpx.Response:
        raise httpx.ReadTimeout("slow")

    set_access_token(TOKEN)
    try:
        with pytest.raises(BackendUnavailableError):
            await search_memory(
                Principal(org_id=ORG_A, permissions=MEMORY_READ, agent_id=AGENT),
                parse_search_args({"query": "q"}),
                memory_client_for(handler),
            )
    finally:
        set_access_token(None)


@pytest.mark.asyncio
async def test_search_unconfigured_client() -> None:
    set_access_token(TOKEN)
    try:
        with pytest.raises(BackendUnavailableError, match="IBEX_MEMORY_HTTP_URL"):
            await search_memory(
                Principal(org_id=ORG_A, permissions=MEMORY_READ, agent_id=AGENT),
                parse_search_args({"query": "q"}),
                None,
            )
    finally:
        set_access_token(None)


@pytest.mark.asyncio
async def test_write_unconfigured_and_timeout() -> None:
    set_access_token(TOKEN)
    try:
        with pytest.raises(BackendUnavailableError):
            await write_memory(
                Principal(org_id=ORG_A, permissions=MEMORY_WRITE, agent_id=AGENT),
                parse_write_args({"content": "c"}),
                None,
            )
    finally:
        set_access_token(None)

    def handler(_request: httpx.Request) -> httpx.Response:
        raise httpx.ReadTimeout("slow")

    set_access_token(TOKEN)
    try:
        with pytest.raises(BackendUnavailableError):
            await write_memory(
                Principal(org_id=ORG_A, permissions=MEMORY_WRITE, agent_id=AGENT),
                parse_write_args({"content": "c"}),
                memory_client_for(handler),
            )
    finally:
        set_access_token(None)


@pytest.mark.asyncio
async def test_search_transport_maps_unavailable() -> None:
    def handler(_request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("down")

    set_access_token(TOKEN)
    try:
        with pytest.raises(BackendUnavailableError):
            await search_memory(
                Principal(org_id=ORG_A, permissions=MEMORY_READ, agent_id=AGENT),
                parse_search_args({"query": "q"}),
                memory_client_for(handler),
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
        return create_memory_response(memory_id=mid, org_id=ORG_A, agent_id=AGENT)

    set_access_token(TOKEN)
    try:
        principal = Principal(org_id=ORG_A, permissions=MEMORY_WRITE, agent_id=AGENT)
        args = parse_write_args({"content": "remember", "category": "factual"})
        client = memory_client_for(handler)
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
