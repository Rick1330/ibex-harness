"""Schema, parsing, and handler tests for the get_memory_lineage tool."""

from __future__ import annotations

from uuid import UUID, uuid4

import httpx
import pytest

from app.access_token import set_access_token
from app.agent_verifier import AllowAllAgentVerifier, StaticAgentVerifier
from app.errors import (
    BackendRejectedError,
    BackendUnavailableError,
    PermissionDeniedError,
    SchemaError,
)
from app.permissions import MEMORY_READ, MEMORY_WRITE
from app.principal import Principal
from app.tools import (
    GET_MEMORY_LINEAGE_SCHEMA,
    get_memory_lineage,
    parse_lineage_args,
)
from tests.memory_fixtures import (
    LineageEdgeSpec,
    LineageResponseSpec,
    lineage_response,
    memory_client_for,
)

ORG_A = UUID("aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa")
AGENT = UUID("cccccccc-cccc-cccc-cccc-cccccccccccc")
TOKEN = "tok-test"
_ALLOW = AllowAllAgentVerifier()


def test_lineage_schema_is_closed_and_bounded() -> None:
    assert GET_MEMORY_LINEAGE_SCHEMA["additionalProperties"] is False
    assert GET_MEMORY_LINEAGE_SCHEMA["required"] == ["memory_id"]
    depth = GET_MEMORY_LINEAGE_SCHEMA["properties"]["max_depth"]
    assert depth["minimum"] == 1
    assert depth["maximum"] == 5
    assert depth["default"] == 3


@pytest.mark.parametrize(
    "raw",
    [
        {},
        {"memory_id": str(AGENT), "max_depth": 0},
        {"memory_id": str(AGENT), "max_depth": 6},
        {"memory_id": "not-a-uuid"},
        {"memory_id": str(AGENT), "unexpected": 1},
    ],
)
def test_parse_lineage_args_rejects_bad_input(raw: dict[str, object]) -> None:
    with pytest.raises(SchemaError):
        parse_lineage_args(raw)


def test_parse_lineage_args_defaults_depth() -> None:
    assert parse_lineage_args({"memory_id": str(AGENT)}).max_depth == 3


@pytest.mark.asyncio
async def test_get_memory_lineage_success() -> None:
    mid = str(uuid4())

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == f"/v1/memories/{mid}/lineage"
        return lineage_response(
            LineageResponseSpec(
                memory_id=mid,
                edges=(LineageEdgeSpec(relationship_type="specializes", depth=2),),
                max_depth=4,
            )
        )

    set_access_token(TOKEN)
    try:
        out = await get_memory_lineage(
            Principal(org_id=ORG_A, permissions=MEMORY_READ, agent_id=AGENT),
            parse_lineage_args({"memory_id": mid, "max_depth": 4}),
            memory_client_for(handler),
            _ALLOW,
        )
    finally:
        set_access_token(None)

    assert out["org_id"] == str(ORG_A)
    assert out["memory_id"] == mid
    assert out["max_depth"] == 4
    assert out["truncated"] is False
    edge = out["edges"][0]
    assert edge["relationship_type"] == "specializes"
    assert edge["from_memory_id"] == mid
    assert edge["other"]["memory_id"] == str(UUID(edge["target_memory_id"]))
    assert edge["other"]["status"] == "superseded"


@pytest.mark.asyncio
async def test_get_memory_lineage_requires_memory_read() -> None:
    principal = Principal(org_id=ORG_A, permissions=MEMORY_WRITE, agent_id=AGENT)
    set_access_token(TOKEN)
    try:
        with pytest.raises(PermissionDeniedError):
            await get_memory_lineage(
                principal,
                parse_lineage_args({"memory_id": str(AGENT)}),
                memory_client_for(lambda _request: lineage_response()),
            )
    finally:
        set_access_token(None)


@pytest.mark.asyncio
async def test_get_memory_lineage_not_visible_maps_to_not_found() -> None:
    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(404, text="nope")

    set_access_token(TOKEN)
    try:
        with pytest.raises(BackendRejectedError) as excinfo:
            await get_memory_lineage(
                Principal(org_id=ORG_A, permissions=MEMORY_READ, agent_id=AGENT),
                parse_lineage_args({"memory_id": str(AGENT)}),
                memory_client_for(handler),
                _ALLOW,
            )
    finally:
        set_access_token(None)
    assert excinfo.value.code == "not_found"
    # The MCP wire format has no structured code field: the text is the contract.
    assert "not_found" in str(excinfo.value)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("client", "verifier"),
    [
        (None, _ALLOW),
        (memory_client_for(lambda _request: lineage_response()), None),
    ],
    ids=["no_memory_client", "no_agent_verifier"],
)
async def test_get_memory_lineage_configuration_gaps_fail_closed(client, verifier) -> None:
    set_access_token(TOKEN)
    try:
        with pytest.raises(BackendUnavailableError):
            await get_memory_lineage(
                Principal(org_id=ORG_A, permissions=MEMORY_READ, agent_id=AGENT),
                parse_lineage_args({"memory_id": str(AGENT)}),
                client,
                verifier,
            )
    finally:
        set_access_token(None)


@pytest.mark.asyncio
async def test_get_memory_lineage_denies_a_not_active_agent() -> None:
    """A suspended agent must not read lineage: no lower layer checks it."""
    outbound: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        outbound.append(request)
        return lineage_response()

    deny = StaticAgentVerifier(allowed=set(), deny_message="agent is not active")
    set_access_token(TOKEN)
    try:
        with pytest.raises(PermissionDeniedError, match="not active"):
            await get_memory_lineage(
                Principal(org_id=ORG_A, permissions=MEMORY_READ, agent_id=AGENT),
                parse_lineage_args({"memory_id": str(AGENT)}),
                memory_client_for(handler),
                deny,
            )
    finally:
        set_access_token(None)
    assert outbound == []
