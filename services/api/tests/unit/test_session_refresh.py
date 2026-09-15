"""Unit tests for Auth-owned operator session refresh (protobuf + gRPC mapping)."""

from __future__ import annotations

from contextlib import asynccontextmanager
from unittest.mock import AsyncMock, MagicMock, patch

import grpc
import pytest
from authclient.codec import AuthCodecError, encode_varint
from authclient.errors import AuthFailedError, AuthUnavailableError

from app.auth.session_refresh import (
    _decode_string_field,
    encode_issue_with_refresh,
    refresh_operator_session,
)


def _proto_string(field_num: int, value: str) -> bytes:
    raw = value.encode("utf-8")
    return encode_varint((field_num << 3) | 2) + encode_varint(len(raw)) + raw


def _proto_varint(field_num: int, value: int) -> bytes:
    return encode_varint((field_num << 3) | 0) + encode_varint(value)


def test_encode_issue_with_refresh_multi_byte() -> None:
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


def test_decode_string_field_multi_byte_key_and_length() -> None:
    long_val = "x" * 200
    # Field 16 requires a multi-byte protobuf key; length >= 128 is multi-byte too.
    buf = _proto_varint(7, 300) + _proto_string(16, long_val) + _proto_string(1, "access")
    assert _decode_string_field(buf, 16) == long_val
    assert _decode_string_field(buf, 1) == "access"


def test_decode_string_field_skips_fixed64() -> None:
    # wire type 1 (64-bit) is skipped, then field 1 is found.
    buf = bytes([0x09, 0, 0, 0, 0, 0, 0, 0, 0]) + _proto_string(1, "ok")
    assert _decode_string_field(buf, 1) == "ok"


def test_decode_string_field_rejects_unsupported_wire() -> None:
    with pytest.raises(AuthCodecError, match="unsupported wire type"):
        _decode_string_field(bytes([0x0F]), 1)


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


@pytest.mark.asyncio
async def test_refresh_operator_session_codec_error_maps_unavailable() -> None:
    stub = AsyncMock(return_value=bytes([0x0F]))
    with _patch_channel(stub), pytest.raises(AuthUnavailableError, match="codec"):
        await refresh_operator_session(auth_grpc_addr="127.0.0.1:50051", refresh_token="r")


def test_decode_string_field_skips_fixed32() -> None:
    # wire type 5 (32-bit) then field 1.
    buf = bytes([0x0D, 1, 2, 3, 4]) + _proto_string(1, "ok")
    assert _decode_string_field(buf, 1) == "ok"


def test_decode_string_field_rejects_oversized_message() -> None:
    from app.auth import session_refresh as mod

    huge = b"\x00" * (mod._MAX_MESSAGE + 1)
    with pytest.raises(AuthCodecError, match="too large"):
        _decode_string_field(huge, 1)


def test_decode_string_field_rejects_truncated_varint_and_len() -> None:
    with pytest.raises(AuthCodecError, match="truncated varint"):
        _decode_string_field(bytes([0x80]), 1)
    # length-delimited key for field 1, then truncated length/body
    with pytest.raises(AuthCodecError, match="truncated"):
        _decode_string_field(bytes([0x0A, 0x05, 0x01]), 1)


def test_decode_string_field_rejects_field_over_max_token() -> None:
    from app.auth import session_refresh as mod

    raw = b"x" * (mod._MAX_TOKEN_FIELD + 1)
    buf = encode_varint((1 << 3) | 2) + encode_varint(len(raw)) + raw
    with pytest.raises(AuthCodecError, match="exceeds limit"):
        _decode_string_field(buf, 1)


def test_decode_string_field_skips_length_delimited_other_field() -> None:
    buf = _proto_string(9, "skip-me") + _proto_string(1, "access")
    assert _decode_string_field(buf, 1) == "access"


def test_decode_string_field_rejects_overlong_varint() -> None:
    # 10 continuation bytes → shift > 63
    with pytest.raises(AuthCodecError, match="invalid varint"):
        _decode_string_field(bytes([0x80] * 10), 1)


def test_decode_string_field_rejects_truncated_fixed64() -> None:
    with pytest.raises(AuthCodecError, match="truncated fixed64"):
        _decode_string_field(bytes([0x09, 1, 2, 3]), 1)


def test_decode_string_field_rejects_truncated_fixed32() -> None:
    with pytest.raises(AuthCodecError, match="truncated fixed32"):
        _decode_string_field(bytes([0x0D, 1, 2]), 1)


@pytest.mark.asyncio
async def test_refresh_operator_session_empty_tokens() -> None:
    stub = AsyncMock(return_value=_proto_string(1, "") + _proto_string(2, ""))
    with _patch_channel(stub), pytest.raises(AuthUnavailableError, match="incomplete"):
        await refresh_operator_session(auth_grpc_addr="127.0.0.1:50051", refresh_token="r")


@pytest.mark.asyncio
async def test_refresh_operator_session_auth_codec_error_from_rpc() -> None:
    stub = AsyncMock(side_effect=AuthCodecError("boom"))
    with _patch_channel(stub), pytest.raises(AuthUnavailableError, match="codec"):
        await refresh_operator_session(auth_grpc_addr="127.0.0.1:50051", refresh_token="r")
