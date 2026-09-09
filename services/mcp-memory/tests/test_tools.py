"""Tool schema, agent resolution, and memory-HTTP handler tests."""

from __future__ import annotations

import json
from collections.abc import Callable
from uuid import UUID, uuid4

import httpx
import pytest

from app.access_token import get_access_token, require_access_token, set_access_token
from app.agent_verifier import AllowAllAgentVerifier, StaticAgentVerifier
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
    RECORD_FEEDBACK_SCHEMA,
    SEARCH_MEMORY_SCHEMA,
    WRITE_MEMORY_SCHEMA,
    parse_feedback_args,
    parse_search_args,
    parse_write_args,
    record_feedback,
    resolve_tool_agent_id,
    search_memory,
    write_idempotency_key,
    write_memory,
)
from tests.memory_fixtures import CreatedMemory, create_memory_response, memory_client_for

ORG_A = UUID("aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa")
ORG_B = UUID("bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb")
AGENT = UUID("cccccccc-cccc-cccc-cccc-cccccccccccc")
AGENT_OTHER = UUID("dddddddd-dddd-dddd-dddd-dddddddddddd")
TOKEN = "tok-test"
_ALLOW = AllowAllAgentVerifier()


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
    assert RECORD_FEEDBACK_SCHEMA["additionalProperties"] is False
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


@pytest.mark.asyncio
@pytest.mark.parametrize("tool", ["search", "write"])
async def test_agent_scoped_token_rejects_foreign_agent_id_before_memory_http(
    tool: str,
) -> None:
    """Agent-binding regression (formerly mislabeled ISO-MCP-01).

    Agent-scoped PATs deny a mismatched tool agent_id in resolve_tool_agent_id
    before ValidateAgent. Kept as a non-ISO regression so ISO-MCP-01 can own the
    org-scoped → ValidateAgent cross-org path.
    """
    outbound: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        outbound.append(request)
        return httpx.Response(200, json={"data": {"results": [], "id": str(uuid4())}})

    # AllowAll would pass ValidateAgent — denial must come from binding only.
    principal = Principal(org_id=ORG_A, permissions=MEMORY_READ | MEMORY_WRITE, agent_id=AGENT)
    client = memory_client_for(handler)
    if tool == "search":
        call = search_memory(
            principal,
            parse_search_args({"query": "q", "agent_id": str(AGENT_OTHER)}),
            client,
            _ALLOW,
        )
    else:
        call = write_memory(
            principal,
            parse_write_args({"content": "x", "agent_id": str(AGENT_OTHER)}),
            client,
            _ALLOW,
        )
    set_access_token(TOKEN)
    try:
        with pytest.raises(
            PermissionDeniedError, match="not authorized for the requested agent"
        ):
            await call
    finally:
        set_access_token(None)
    assert outbound == []


@pytest.mark.asyncio
async def test_org_scoped_foreign_agent_reaches_verifier_not_binding() -> None:
    """Sanity: org-scoped + foreign agent_id is not stopped by resolve_tool_agent_id.

    With AllowAll, memory HTTP is reached (proves ISO-MCP-01 would greenwash if
    ValidateAgent were stubbed to allow-all). With a denying verifier, zero outbound.
    """
    outbound: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        outbound.append(request)
        return httpx.Response(200, json={"data": {"results": []}})

    principal = Principal(org_id=ORG_A, permissions=MEMORY_READ, agent_id=None)
    args = parse_search_args({"query": "cross", "agent_id": str(AGENT_OTHER)})
    client = memory_client_for(handler)

    set_access_token(TOKEN)
    try:
        out = await search_memory(principal, args, client, _ALLOW)
    finally:
        set_access_token(None)
    assert out["results"] == []
    assert len(outbound) == 1

    outbound.clear()
    deny = StaticAgentVerifier(allowed=set(), deny_message="agent not authorized")
    set_access_token(TOKEN)
    try:
        with pytest.raises(PermissionDeniedError, match="agent not authorized"):
            await search_memory(principal, args, client, deny)
    finally:
        set_access_token(None)
    assert outbound == []


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


def _status_handler(status: int) -> Callable[[httpx.Request], httpx.Response]:
    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(status, text="err")

    return handler


def _timeout_handler(_request: httpx.Request) -> httpx.Response:
    raise httpx.ReadTimeout("slow")


def _transport_handler(_request: httpx.Request) -> httpx.Response:
    raise httpx.ConnectError("down")


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("tool", "permissions", "raw"),
    [
        ("search", 0, {"query": "q"}),
        ("write", MEMORY_READ, {"content": "c"}),
    ],
)
async def test_local_permission_gate_skips_http(
    tool: str, permissions: int, raw: dict
) -> None:
    principal = Principal(org_id=ORG_A, permissions=permissions, agent_id=AGENT)
    hits = {"n": 0}

    def counting(_request: httpx.Request) -> httpx.Response:
        hits["n"] += 1
        return httpx.Response(200, json={"data": {"results": []}})

    client = memory_client_for(counting)
    if tool == "search":
        coro = search_memory(principal, parse_search_args(raw), client, _ALLOW)
    else:
        coro = write_memory(principal, parse_write_args(raw), client, _ALLOW)
    with pytest.raises(PermissionDeniedError):
        await coro
    assert hits["n"] == 0


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
            _ALLOW,
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
            _ALLOW,
        )
    finally:
        set_access_token(None)
    assert out["results"] == []


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("tool", "principal"),
    [
        (
            "search",
            Principal(org_id=ORG_A, permissions=MEMORY_READ, agent_id=AGENT),
        ),
        (
            "write",
            Principal(org_id=ORG_A, permissions=MEMORY_WRITE, agent_id=AGENT),
        ),
        (
            "feedback",
            Principal(org_id=ORG_A, permissions=MEMORY_WRITE, agent_id=AGENT),
        ),
    ],
)
async def test_inactive_agent_denied_before_memory_http(
    tool: str,
    principal: Principal,
) -> None:
    """ISO-MCP-03 unit: suspended/inactive verifier fails closed without memory I/O."""
    outbound: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        outbound.append(request)
        return httpx.Response(200, json={"data": {"results": [], "id": str(uuid4())}})

    deny = StaticAgentVerifier(allowed=set(), deny_message="agent is not active")
    client = memory_client_for(handler)
    if tool == "search":
        call = search_memory(
            principal, parse_search_args({"query": "q"}), client, deny
        )
    elif tool == "write":
        call = write_memory(
            principal, parse_write_args({"content": "note"}), client, deny
        )
    else:
        mid = uuid4()
        call = record_feedback(
            principal,
            parse_feedback_args({"memory_id": str(mid), "feedback": "positive"}),
            client,
            deny,
        )
    set_access_token(TOKEN)
    try:
        with pytest.raises(PermissionDeniedError, match="agent is not active"):
            await call
    finally:
        set_access_token(None)
    assert outbound == []


@pytest.mark.asyncio
async def test_active_agent_verifier_allows_search() -> None:
    """Active agents continue to memory HTTP unchanged after ValidateAgent."""
    allow = StaticAgentVerifier(allowed={(ORG_A, AGENT)})

    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"data": {"results": []}})

    set_access_token(TOKEN)
    try:
        out = await search_memory(
            Principal(org_id=ORG_A, permissions=MEMORY_READ, agent_id=AGENT),
            parse_search_args({"query": "ok"}),
            memory_client_for(handler),
            allow,
        )
    finally:
        set_access_token(None)
    assert out["results"] == []


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("handler", "exc_type"),
    [
        (_status_handler(503), BackendUnavailableError),
        (_status_handler(403), PermissionDeniedError),
        (_status_handler(401), AuthFailedError),
        (_status_handler(409), BackendRejectedError),
        (_timeout_handler, BackendUnavailableError),
        (_transport_handler, BackendUnavailableError),
    ],
)
async def test_search_backend_fail_closed(
    handler: Callable[[httpx.Request], httpx.Response],
    exc_type: type[BaseException],
) -> None:
    principal = Principal(org_id=ORG_A, permissions=MEMORY_READ, agent_id=AGENT)
    args = parse_search_args({"query": "q"})
    client = memory_client_for(handler)
    set_access_token(TOKEN)
    try:
        with pytest.raises(exc_type):
            await search_memory(principal, args, client, _ALLOW)
    finally:
        set_access_token(None)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("tool", "mode", "match"),
    [
        ("search", "unset", "IBEX_MEMORY_HTTP_URL"),
        ("write", "unset", None),
        ("write", "timeout", None),
    ],
)
async def test_tool_dependency_unavailable(
    tool: str, mode: str, match: str | None
) -> None:
    """Unset URL and write-path timeouts fail closed without inventing success."""
    client = None if mode == "unset" else memory_client_for(_timeout_handler)
    set_access_token(TOKEN)
    try:
        if tool == "search":
            call = search_memory(
                Principal(org_id=ORG_A, permissions=MEMORY_READ, agent_id=AGENT),
                parse_search_args({"query": "q"}),
                client,
                _ALLOW,
            )
        else:
            call = write_memory(
                Principal(org_id=ORG_A, permissions=MEMORY_WRITE, agent_id=AGENT),
                parse_write_args({"content": "c"}),
                client,
                _ALLOW,
            )
        if match is None:
            with pytest.raises(BackendUnavailableError):
                await call
        else:
            with pytest.raises(BackendUnavailableError, match=match):
                await call
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
        return create_memory_response(
            CreatedMemory(memory_id=mid, org_id=ORG_A, agent_id=AGENT)
        )

    set_access_token(TOKEN)
    try:
        principal = Principal(org_id=ORG_A, permissions=MEMORY_WRITE, agent_id=AGENT)
        args = parse_write_args({"content": "remember", "category": "factual"})
        client = memory_client_for(handler)
        first = await write_memory(principal, args, client, _ALLOW)
        second = await write_memory(principal, args, client, _ALLOW)
    finally:
        set_access_token(None)

    assert first["memory_id"] == mid
    assert first["persisted"] is True
    assert first["mcp_source"] == "mcp_explicit"
    assert first["source"] == "user_provided"
    assert bodies[0]["metadata"] == {"mcp_source": "mcp_explicit"}
    assert "source" not in bodies[0]
    assert bodies[0]["confidence"] == 0.6
    assert "org_id" not in bodies[0]
    assert seen_keys[0] == seen_keys[1]
    assert seen_keys[0] == write_idempotency_key(
        org_id=ORG_A, agent_id=AGENT, content="remember"
    )
    assert second["memory_id"] == mid


@pytest.mark.parametrize(
    ("parser", "raw"),
    [
        (parse_search_args, {}),
        (parse_search_args, {"query": 1}),
        (parse_search_args, {"query": "x" * 2001}),
        (parse_write_args, {}),
        (parse_write_args, {"content": 1}),
        (parse_write_args, {"content": "x" * 8001}),
    ],
)
def test_schema_rejects_missing_wrong_type_and_oversized(parser, raw: dict) -> None:
    with pytest.raises(SchemaError):
        parser(raw)


def test_feedback_schema_rejects_extra() -> None:
    with pytest.raises(SchemaError):
        parse_feedback_args({"memory_id": str(AGENT), "feedback": "positive", "extra": 1})


def test_feedback_schema_rejects_bad_enum() -> None:
    with pytest.raises(SchemaError):
        parse_feedback_args({"memory_id": str(AGENT), "feedback": "great"})


def test_feedback_schema_accepts_optional_fields() -> None:
    args = parse_feedback_args(
        {
            "memory_id": str(AGENT),
            "feedback": "neutral",
            "notes": "ok",
            "session_id": str(AGENT),
        }
    )
    assert args.feedback == "neutral"
    assert args.notes == "ok"


@pytest.mark.asyncio
async def test_record_feedback_requires_memory_write() -> None:
    principal = Principal(org_id=ORG_A, permissions=MEMORY_READ, agent_id=AGENT)
    hits = {"n": 0}

    def counting(_request: httpx.Request) -> httpx.Response:
        hits["n"] += 1
        return httpx.Response(200, json={"data": {}})

    args = parse_feedback_args({"memory_id": str(AGENT), "feedback": "positive"})
    client = memory_client_for(counting)
    with pytest.raises(PermissionDeniedError):
        await record_feedback(principal, args, client, _ALLOW)
    assert hits["n"] == 0


@pytest.mark.asyncio
async def test_record_feedback_org_scoped_skips_agent_verify() -> None:
    """Org-scoped PATs (no agent_id) rely on MEMORY_WRITE only."""
    outbound: list[httpx.Request] = []
    mid = str(uuid4())

    def handler(request: httpx.Request) -> httpx.Response:
        outbound.append(request)
        return httpx.Response(
            200,
            json={
                "data": {
                    "memory_id": mid,
                    "feedback": "positive",
                    "new_usefulness_score": 0.5,
                    "total_positive_feedback": 1,
                    "total_negative_feedback": 0,
                }
            },
        )

    deny_all = StaticAgentVerifier(allowed=set())
    set_access_token(TOKEN)
    try:
        out = await record_feedback(
            Principal(org_id=ORG_A, permissions=MEMORY_WRITE, agent_id=None),
            parse_feedback_args(
                {
                    "memory_id": mid,
                    "feedback": "positive",
                    "session_id": str(AGENT),
                    "trace_id": str(ORG_A),
                    "notes": "n",
                }
            ),
            memory_client_for(handler),
            deny_all,
        )
    finally:
        set_access_token(None)
    assert out["memory_id"] == mid
    assert len(outbound) == 1
    body = json.loads(outbound[0].content)
    assert body["session_id"] == str(AGENT)
    assert body["trace_id"] == str(ORG_A)
    assert body["notes"] == "n"


@pytest.mark.asyncio
async def test_record_feedback_success() -> None:
    mid = str(uuid4())

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.headers["Authorization"] == f"Bearer {TOKEN}"
        assert request.url.path.endswith(f"/memories/{mid}/feedback")
        body = json.loads(request.content)
        assert body == {"feedback": "positive", "notes": "helped"}
        return httpx.Response(
            200,
            json={
                "data": {
                    "memory_id": mid,
                    "feedback": "positive",
                    "new_usefulness_score": 0.67,
                    "total_positive_feedback": 1,
                    "total_negative_feedback": 0,
                }
            },
        )

    set_access_token(TOKEN)
    try:
        out = await record_feedback(
            Principal(org_id=ORG_A, permissions=MEMORY_WRITE, agent_id=AGENT),
            parse_feedback_args(
                {"memory_id": mid, "feedback": "positive", "notes": "helped"}
            ),
            memory_client_for(handler),
            _ALLOW,
        )
    finally:
        set_access_token(None)
    assert out["memory_id"] == mid
    assert out["new_usefulness_score"] == 0.67
    assert out["total_positive_feedback"] == 1


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("handler", "exc_type"),
    [
        (_status_handler(404), BackendRejectedError),
        (_status_handler(503), BackendUnavailableError),
        (_timeout_handler, BackendUnavailableError),
    ],
)
async def test_record_feedback_fail_closed(
    handler: Callable[[httpx.Request], httpx.Response],
    exc_type: type[BaseException],
) -> None:
    principal = Principal(org_id=ORG_A, permissions=MEMORY_WRITE, agent_id=AGENT)
    args = parse_feedback_args({"memory_id": str(AGENT), "feedback": "negative"})
    client = memory_client_for(handler)
    set_access_token(TOKEN)
    try:
        with pytest.raises(exc_type):
            await record_feedback(principal, args, client, _ALLOW)
    finally:
        set_access_token(None)
