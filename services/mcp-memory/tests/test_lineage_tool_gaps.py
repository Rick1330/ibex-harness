"""Failure-path and side-effect gaps for the `get_memory_lineage` MCP tool.

Claims under test (engineering/MCP_SERVER.md, ADR-0094):
* no memory outbound call when the permission bit is missing;
* a 5xx / timeout / malformed body fails closed instead of returning a graph;
* the tool result never carries memory content.
"""

from __future__ import annotations

from typing import Any
from uuid import UUID, uuid4

import httpx
import pytest

from app.access_token import set_access_token
from app.agent_verifier import AllowAllAgentVerifier
from app.audit import AsyncAuditEmitter, MemoryAuditSink
from app.errors import (
    BackendUnavailableError,
    PermissionDeniedError,
)
from app.permissions import MEMORY_READ, MEMORY_WRITE
from app.principal import Principal, set_principal
from app.server import McpServerWiring, build_mcp_server
from app.tools import get_memory_lineage, parse_lineage_args
from tests.memory_fixtures import (
    LineageEdgeSpec,
    LineageResponseSpec,
    lineage_response,
    memory_client_for,
)

_ALLOW = AllowAllAgentVerifier()

ORG = UUID("aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa")
AGENT = UUID("bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb")
TOKEN = "tok-lineage-gap"


@pytest.mark.asyncio
async def test_missing_permission_makes_no_memory_call() -> None:
    calls: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        return lineage_response()

    principal = Principal(org_id=ORG, permissions=MEMORY_WRITE, agent_id=AGENT)
    set_access_token(TOKEN)
    try:
        with pytest.raises(PermissionDeniedError):
            await get_memory_lineage(
                principal,
                parse_lineage_args({"memory_id": str(uuid4())}),
                memory_client_for(handler),
                _ALLOW,
            )
    finally:
        set_access_token(None)

    assert calls == [], "the tool called the memory service before checking MemoryRead"


def _status_handler(status: int):
    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(status, text="err")

    return handler


def _timeout_handler(_request: httpx.Request) -> httpx.Response:
    raise httpx.ReadTimeout("too slow")


def _malformed_handler(_request: httpx.Request) -> httpx.Response:
    return httpx.Response(
        200,
        json={"data": {"memory_id": str(uuid4()), "edges": "not-a-list"}},
    )


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "handler",
    [
        _status_handler(503),
        _timeout_handler,
        _malformed_handler,
    ],
    ids=["server_error", "timeout", "malformed_body"],
)
async def test_memory_failures_fail_closed(handler) -> None:
    set_access_token(TOKEN)
    try:
        with pytest.raises(BackendUnavailableError) as excinfo:
            await get_memory_lineage(
                Principal(org_id=ORG, permissions=MEMORY_READ, agent_id=AGENT),
                parse_lineage_args({"memory_id": str(uuid4())}),
                memory_client_for(handler),
                _ALLOW,
            )
    finally:
        set_access_token(None)
    assert excinfo.value.code == "backend_unavailable"


@pytest.mark.asyncio
async def test_result_contains_no_memory_content() -> None:
    mid = str(uuid4())

    def handler(_request: httpx.Request) -> httpx.Response:
        return lineage_response(
            LineageResponseSpec(
                memory_id=mid,
                edges=(LineageEdgeSpec(relationship_type="supersedes"),),
            )
        )

    set_access_token(TOKEN)
    try:
        out = await get_memory_lineage(
            Principal(org_id=ORG, permissions=MEMORY_READ, agent_id=AGENT),
            parse_lineage_args({"memory_id": mid}),
            memory_client_for(handler),
            _ALLOW,
        )
    finally:
        set_access_token(None)

    assert "content" not in out
    assert set(out) == {
        "org_id",
        "memory_id",
        "status",
        "tombstoned",
        "supersession_tip",
        "max_depth",
        "truncated",
        "edges",
    }
    assert set(out["edges"][0]) == {
        "source_memory_id",
        "target_memory_id",
        "relationship_type",
        "confidence",
        "depth",
        "from_memory_id",
        "other",
    }


def _mcp(client: Any) -> Any:
    sink = MemoryAuditSink()
    audit = AsyncAuditEmitter(sink, maxsize=8)
    return (
        build_mcp_server(
            McpServerWiring(
                audit=audit,
                memory_client=client,
                agent_verifier=AllowAllAgentVerifier(),
            )
        ),
        audit,
        sink,
    )


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("arguments", "match"),
    [
        ({"max_depth": 6}, "[Dd]epth|less than|validation"),
        ({"include_content": True}, "[Ee]xtra|unexpected|validation"),
    ],
    ids=["depth_out_of_range", "undeclared_argument"],
)
async def test_fastmcp_rejects_bad_arguments_without_reaching_memory(
    arguments: dict[str, object],
    match: str,
) -> None:
    calls: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        return lineage_response()

    client = memory_client_for(handler)
    mcp, audit, sink = _mcp(client)
    audit.start()
    set_principal(
        Principal(org_id=ORG, permissions=MEMORY_READ | MEMORY_WRITE, agent_id=AGENT)
    )
    set_access_token(TOKEN)
    try:
        with pytest.raises(Exception, match=match):
            await mcp.call_tool(
                "get_memory_lineage",
                {"memory_id": str(uuid4()), **arguments},
            )
    finally:
        set_principal(None)
        set_access_token(None)
        await audit.aclose()
        await client.aclose()

    assert calls == []
    assert sink.events == []
