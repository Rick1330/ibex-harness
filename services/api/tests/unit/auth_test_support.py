"""Shared helpers for auth client unit tests (api-specific; not a memory copy)."""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from unittest.mock import AsyncMock, MagicMock, patch

import grpc
from authclient import ValidateTokenWire, encode_varint

from app.auth.client import GRPCTokenValidator


def wire_bytes(wire: ValidateTokenWire) -> bytes:
    """Minimal ValidateToken response encoder for unit tests."""
    org = str(wire.org_id).encode()
    chunks = [bytes([0x0A]) + encode_varint(len(org)) + org, bytes([0x10]) + encode_varint(wire.permissions)]
    if wire.agent_id is not None:
        raw = str(wire.agent_id).encode()
        chunks.append(bytes([0x1A]) + encode_varint(len(raw)) + raw)
    if wire.user_id is not None:
        raw = wire.user_id.encode()
        chunks.append(bytes([0x22]) + encode_varint(len(raw)) + raw)
    if wire.token_id is not None:
        raw = wire.token_id.encode()
        chunks.append(bytes([0x2A]) + encode_varint(len(raw)) + raw)
    return b"".join(chunks)


def aio_rpc(code: grpc.StatusCode) -> grpc.aio.AioRpcError:
    return grpc.aio.AioRpcError(code, details="unit-test")


@contextmanager
def patched_validator(
    *,
    side_effect: object | None = None,
    return_value: object | None = None,
) -> Iterator[GRPCTokenValidator]:
    with patch("authclient.validate.grpc.aio.insecure_channel") as factory:
        stub = AsyncMock(side_effect=side_effect, return_value=return_value)
        channel = MagicMock()
        channel.unary_unary.return_value = stub
        channel.close = AsyncMock()
        factory.return_value = channel
        yield GRPCTokenValidator("127.0.0.1:50051", timeout_seconds=0.1)
