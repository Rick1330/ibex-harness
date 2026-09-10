"""Contract tests for GRPCTokenManager error mapping and FakeTokenManager cursors."""

from __future__ import annotations

from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import grpc
import pytest
from authclient.errors import InsufficientPermissionsError, TokenNotFoundError
from authclient.tokens import (
    CreateTokenParams,
    FakeTokenManager,
    GRPCTokenManager,
    TokenMetadataWire,
)

from tests.unit.auth_test_support import aio_rpc


@pytest.mark.asyncio
async def test_fake_manager_offset_cursor_advances() -> None:
    org = str(uuid4())
    mgr = FakeTokenManager()
    now = datetime.now(UTC)
    for i in range(3):
        mgr.seed(
            org,
            TokenMetadataWire(
                token_id=f"00000000-0000-4000-8000-{i:012d}",
                name=f"t{i}",
                prefix="p",
                permissions=1,
                created_at=now,
            ),
        )
    page1 = await mgr.list(org_id=org, access_token="t", limit=2)
    assert len(page1.tokens) == 2
    assert page1.next_cursor == "2"
    page2 = await mgr.list(org_id=org, access_token="t", cursor=page1.next_cursor, limit=2)
    assert len(page2.tokens) == 1
    assert page2.next_cursor == ""
    assert page2.tokens[0].token_id != page1.tokens[0].token_id


@pytest.mark.asyncio
async def test_grpc_token_manager_maps_create_permission_denied() -> None:
    with patch("authclient.tokens.grpc.aio.insecure_channel") as chan_mock:
        channel = MagicMock()
        create_stub = AsyncMock(side_effect=aio_rpc(grpc.StatusCode.PERMISSION_DENIED))
        list_stub = AsyncMock()
        revoke_stub = AsyncMock()
        channel.unary_unary.side_effect = [create_stub, list_stub, revoke_stub]
        chan_mock.return_value = channel
        mgr = GRPCTokenManager("127.0.0.1:50051", timeout_seconds=0.05)
        with pytest.raises(InsufficientPermissionsError):
            await mgr.create(
                CreateTokenParams(
                    org_id=str(uuid4()),
                    name="x",
                    permissions=1,
                    access_token="tok",
                )
            )


@pytest.mark.asyncio
async def test_grpc_token_manager_strict_revoke_not_found() -> None:
    with patch("authclient.tokens.grpc.aio.insecure_channel") as chan_mock:
        channel = MagicMock()
        create_stub = AsyncMock()
        list_stub = AsyncMock()
        revoke_stub = AsyncMock(side_effect=aio_rpc(grpc.StatusCode.NOT_FOUND))
        channel.unary_unary.side_effect = [create_stub, list_stub, revoke_stub]
        chan_mock.return_value = channel
        mgr = GRPCTokenManager("127.0.0.1:50051", timeout_seconds=0.05)
        with pytest.raises(TokenNotFoundError):
            await mgr.revoke_strict(
                org_id=str(uuid4()),
                token_id=str(uuid4()),
                access_token="tok",
            )


@pytest.mark.asyncio
async def test_grpc_token_manager_list_permission_denied_is_not_found() -> None:
    with patch("authclient.tokens.grpc.aio.insecure_channel") as chan_mock:
        channel = MagicMock()
        create_stub = AsyncMock()
        list_stub = AsyncMock(side_effect=aio_rpc(grpc.StatusCode.PERMISSION_DENIED))
        revoke_stub = AsyncMock()
        channel.unary_unary.side_effect = [create_stub, list_stub, revoke_stub]
        chan_mock.return_value = channel
        mgr = GRPCTokenManager("127.0.0.1:50051", timeout_seconds=0.05)
        with pytest.raises(TokenNotFoundError):
            await mgr.list(org_id=str(uuid4()), access_token="tok")
