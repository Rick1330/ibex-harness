"""Unit tests for Auth-owned operator session refresh (protobuf + gRPC mapping)."""

from __future__ import annotations

from contextlib import asynccontextmanager
from unittest.mock import AsyncMock, MagicMock, patch

import grpc
import pytest
from authclient.errors import AuthFailedError, AuthUnavailableError

from app.auth.session_refresh import (
    _decode_string_field,
    _encode_varint,
    encode_issue_with_refresh,
    refresh_operator_session,
)


def _proto_string(field_num: int, value: str) -> bytes:
    raw = value.encode("utf-8")
    return bytes([(field_num << 3) | 2]) + _encode_varint(len(raw)) + raw


def _proto_varint(field_num: int, value: int) -> bytes:
    return bytes([(field_num << 3) | 0]) + _encode_varint(value)


def test_encode_varint_multi_byte() -> None:
    assert _encode_varint(0) == b"\x00"
    assert _encode_varint(127) == b"\x7f"
    assert _encode_varint(128) == b"\x80\x01"
    long_tok = "r" * 200
    payload = encode_issue_with_refresh(long_tok)
    assert payload[0] == 0x0A
    assert long_tok.encode() in payload


def test_decode_string_field_skips_other_fields_and_varints() -> None:
    buf = (
        _proto_varint(3, 42)
        + _proto_string(1, "access-token")
        + _proto_string(2, "refresh-token")
    )
    assert _decode_string_field(buf, 1) == "access-token"
    assert _decode_string_field(buf, 2) == "refresh-token"
    assert _decode_string_field(buf, 9) is None
    assert _decode_string_field(b"", 1) is None


def test_decode_string_field_multi_byte_lengths_and_varints() -> None:
    long_val = "x" * 200
    # Multi-byte string length + multi-byte skipped varint (value >= 128).
    buf = _proto_varint(7, 300) + _proto_string(1, long_val)
    assert _decode_string_field(buf, 1) == long_val


def test_decode_string_field_rejects_unknown_wire_type() -> None:
    # wire type 1 (64-bit) is unsupported → None
    assert _decode_string_field(bytes([0x09, 0, 0, 0, 0, 0, 0, 0, 0]), 1) is None


def _patch_channel(stub: AsyncMock):
    channel = MagicMock()
    channel.unary_unary.return_value = stub

    @asynccontextmanager
    async def _cm(_addr: str):
        yield channel

    return patch("app.auth.session_refresh.grpc.aio.insecure_channel", side_effect=_cm)


@pytest.mark.asyncio
async def test_refresh_operator_session_success() -> None:
    resp = _proto_string(1, "access-rs") + _proto_string(2, "refresh-rs")
    stub = AsyncMock(return_value=resp)
    with _patch_channel(stub):
        pair = await refresh_operator_session(
            auth_grpc_addr="127.0.0.1:50051",
            refresh_token="old-refresh",
        )
    assert pair.access_token == "access-rs"
    assert pair.refresh_token == "refresh-rs"
    stub.assert_awaited_once()


@pytest.mark.asyncio
async def test_refresh_operator_session_timeout() -> None:
    stub = AsyncMock(side_effect=TimeoutError())
    with _patch_channel(stub), pytest.raises(AuthUnavailableError, match="timeout"):
        await refresh_operator_session(
            auth_grpc_addr="localhost:50051",
            refresh_token="r",
            timeout_seconds=0.01,
        )


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("code", "exc_type", "match"),
    [
        (grpc.StatusCode.UNAVAILABLE, AuthUnavailableError, "unavailable"),
        (grpc.StatusCode.DEADLINE_EXCEEDED, AuthUnavailableError, "unavailable"),
        (grpc.StatusCode.UNAUTHENTICATED, AuthFailedError, "invalid refresh"),
        (grpc.StatusCode.PERMISSION_DENIED, AuthFailedError, "invalid refresh"),
        (grpc.StatusCode.INTERNAL, AuthUnavailableError, "refresh failed"),
    ],
)
async def test_refresh_operator_session_rpc_errors(code, exc_type, match) -> None:
    stub = AsyncMock(side_effect=grpc.aio.AioRpcError(code, details="boom"))
    with _patch_channel(stub), pytest.raises(exc_type, match=match):
        await refresh_operator_session(auth_grpc_addr="127.0.0.1:50051", refresh_token="r")


@pytest.mark.asyncio
async def test_refresh_operator_session_incomplete_response() -> None:
    stub = AsyncMock(return_value=_proto_string(1, "access-only"))
    with _patch_channel(stub), pytest.raises(AuthUnavailableError, match="incomplete"):
        await refresh_operator_session(auth_grpc_addr="127.0.0.1:50051", refresh_token="r")
