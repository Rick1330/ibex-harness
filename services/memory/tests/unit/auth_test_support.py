"""Shared helpers for auth client and proto wire unit tests."""

from __future__ import annotations

from contextlib import contextmanager
from unittest.mock import AsyncMock, MagicMock, patch

import grpc

from app.auth.client import GRPCTokenValidator
from app.auth.proto_wire import ValidateTokenWire, _encode_varint


def encode_validate_token_wire(wire: ValidateTokenWire) -> bytes:
    parts: list[bytes] = []
    parts.append(bytes([0x0A]) + _encode_varint(len(str(wire.org_id))) + str(wire.org_id).encode())
    parts.append(bytes([0x10]) + _encode_varint(wire.permissions))
    if wire.agent_id is not None:
        aid = str(wire.agent_id).encode()
        parts.append(bytes([0x1A]) + _encode_varint(len(aid)) + aid)
    if wire.user_id is not None:
        uid = wire.user_id.encode()
        parts.append(bytes([0x22]) + _encode_varint(len(uid)) + uid)
    if wire.token_id is not None:
        tid = wire.token_id.encode()
        parts.append(bytes([0x2A]) + _encode_varint(len(tid)) + tid)
    return b"".join(parts)


def rpc_error(code: grpc.StatusCode) -> grpc.aio.AioRpcError:
    return grpc.aio.AioRpcError(code, details="test")


@contextmanager
def grpc_validator(*, side_effect: object | None = None, return_value: object | None = None):
    with patch("app.auth.client.grpc.aio.insecure_channel") as chan_mock:
        stub = AsyncMock(side_effect=side_effect, return_value=return_value)
        channel = MagicMock()
        channel.unary_unary.return_value = stub
        channel.close = AsyncMock()
        chan_mock.return_value = channel
        yield GRPCTokenValidator("127.0.0.1:50051", timeout_seconds=0.1)
