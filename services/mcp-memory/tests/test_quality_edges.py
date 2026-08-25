"""Extra coverage for audit shutdown and wire codec edges."""

from __future__ import annotations

from uuid import UUID

import pytest

from app.audit import AsyncAuditEmitter, MemoryAuditSink, ToolCallAuditEvent
from app.errors import AuthUnavailableError, SchemaError
from app.middleware import _origin_from_resource
from app.proto_wire import decode_validate_token_response, encode_validate_token_request
from app.tools import parse_search_args

ORG = UUID("11111111-1111-1111-1111-111111111111")


def test_origin_from_resource_without_mcp_suffix() -> None:
    assert _origin_from_resource("https://mcp.example.com") == "https://mcp.example.com"


def test_origin_from_resource_strips_mcp() -> None:
    assert _origin_from_resource("https://mcp.example.com/mcp") == "https://mcp.example.com"


def test_encode_token_too_large() -> None:
    with pytest.raises(AuthUnavailableError):
        encode_validate_token_request("x" * 9000)


def test_decode_skips_fixed32() -> None:
    org = "11111111-1111-1111-1111-111111111111"
    org_b = org.encode()
    # field 8 wire32 (tag 0x45) + 4 bytes, then org
    payload = b"\x45" + (b"\x00" * 4)
    payload += b"\x0a" + bytes([len(org_b)]) + org_b
    got = decode_validate_token_response(payload)
    assert got.org_id == UUID(org)


def test_schema_error_message_includes_loc() -> None:
    with pytest.raises(SchemaError) as exc:
        parse_search_args({})
    assert "query" in str(exc.value)


@pytest.mark.asyncio
async def test_audit_aclose_without_start() -> None:
    sink = MemoryAuditSink()
    emitter = AsyncAuditEmitter(sink, maxsize=2)
    await emitter.aclose()


@pytest.mark.asyncio
async def test_audit_emit_after_close_drops() -> None:
    sink = MemoryAuditSink()
    emitter = AsyncAuditEmitter(sink, maxsize=2)
    emitter.start()
    await emitter.aclose()
    emitter.emit(
        ToolCallAuditEvent(
            request_id="x",
            org_id=ORG,
            tool_name="search_memory",
            latency_ms=1,
            success=True,
        )
    )
