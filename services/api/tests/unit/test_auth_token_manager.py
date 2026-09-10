"""Contract tests for GRPCTokenManager error mapping and FakeTokenManager cursors."""

from __future__ import annotations

from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import grpc
import pytest
from authclient.errors import (
    AuthUnavailableError,
    InsufficientPermissionsError,
    TokenNotFoundError,
)
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


def _patched_manager(*, create=None, list_stub=None, revoke=None) -> GRPCTokenManager:
    channel = MagicMock()
    channel.unary_unary.side_effect = [
        create or AsyncMock(),
        list_stub or AsyncMock(),
        revoke or AsyncMock(),
    ]
    with patch("authclient.tokens.grpc.aio.insecure_channel", return_value=channel):
        return GRPCTokenManager("127.0.0.1:50051", timeout_seconds=0.05)


@pytest.mark.asyncio
async def test_grpc_token_manager_maps_create_permission_denied() -> None:
    create_stub = AsyncMock(side_effect=aio_rpc(grpc.StatusCode.PERMISSION_DENIED))
    mgr = _patched_manager(create=create_stub)
    params = CreateTokenParams(
        org_id=str(uuid4()),
        name="x",
        permissions=1,
        access_token="tok",
    )
    with pytest.raises(InsufficientPermissionsError):
        await mgr.create(params)


@pytest.mark.asyncio
async def test_grpc_token_manager_strict_revoke_not_found() -> None:
    revoke_stub = AsyncMock(side_effect=aio_rpc(grpc.StatusCode.NOT_FOUND))
    mgr = _patched_manager(revoke=revoke_stub)
    with pytest.raises(TokenNotFoundError):
        await mgr.revoke_strict(
            org_id=str(uuid4()),
            token_id=str(uuid4()),
            access_token="tok",
        )


@pytest.mark.asyncio
async def test_grpc_token_manager_list_permission_denied_is_not_found() -> None:
    list_stub = AsyncMock(side_effect=aio_rpc(grpc.StatusCode.PERMISSION_DENIED))
    mgr = _patched_manager(list_stub=list_stub)
    with pytest.raises(TokenNotFoundError):
        await mgr.list(org_id=str(uuid4()), access_token="tok")


@pytest.mark.asyncio
async def test_grpc_token_manager_oserror_is_unavailable() -> None:
    create_stub = AsyncMock(side_effect=OSError("down"))
    mgr = _patched_manager(create=create_stub)
    params = CreateTokenParams(
        org_id=str(uuid4()),
        name="x",
        permissions=1,
        access_token="tok",
    )
    with pytest.raises(AuthUnavailableError):
        await mgr.create(params)


@pytest.mark.asyncio
async def test_grpc_token_manager_non_bytes_response_is_unavailable() -> None:
    create_stub = AsyncMock(return_value="not-bytes")
    mgr = _patched_manager(create=create_stub)
    params = CreateTokenParams(
        org_id=str(uuid4()),
        name="x",
        permissions=1,
        access_token="tok",
    )
    with pytest.raises(AuthUnavailableError):
        await mgr.create(params)
