"""Shared protobuf and gRPC plumbing for the session-refresh unit tests.

Both ``test_session_refresh`` (the lifecycle calls) and ``test_step_up_issuance``
(the CreateStepUpToken call) drive ``app.auth.session_refresh`` through a patched
channel with hand-built protobuf bytes, so the encoders, the channel patch and
the single-exception assertion helper live here instead of being copied into
each module.
"""

from __future__ import annotations

import base64
import json
from contextlib import asynccontextmanager
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from authclient.codec import encode_varint

from app.auth.session_refresh import AuthRPC


def _proto_string(field_num: int, value: str) -> bytes:
    raw = value.encode("utf-8")
    return encode_varint((field_num << 3) | 2) + encode_varint(len(raw)) + raw


def _proto_varint(field_num: int, value: int) -> bytes:
    return encode_varint((field_num << 3) | 0) + encode_varint(value)


def _rpc(addr: str = "127.0.0.1:50051", token: str = "", timeout: float = 5.0) -> AuthRPC:
    return AuthRPC(addr, token, timeout)


def _session_token(org_id: str = "org") -> str:
    """JWT-shaped session token carrying only the claim the client reads.

    The lifecycle client names the org it is acting for by reading this claim;
    AuthService is what verifies the signature and compares the two.
    """
    payload = base64.urlsafe_b64encode(json.dumps({"org_id": org_id}).encode()).rstrip(b"=")
    return f"e30.{payload.decode()}.sig"


def _patch_channel(stub: AsyncMock):
    channel = MagicMock()
    channel.unary_unary.return_value = stub

    @asynccontextmanager
    async def _cm(_addr: str, _ca_file: str = ""):
        yield channel

    # session_refresh delegates transport selection to the shared factory.
    return patch("app.auth.session_refresh.open_auth_channel", side_effect=_cm)


async def _assert_rpc_raises(
    stub: AsyncMock,
    awaitable,
    exc_type: type[BaseException],
    match: str,
) -> BaseException:
    """Await under channel patch with a single throwable in pytest.raises (S5914)."""
    patcher = _patch_channel(stub)
    patcher.start()
    try:
        with pytest.raises(exc_type, match=match) as caught:
            await awaitable
        return caught.value
    finally:
        patcher.stop()
