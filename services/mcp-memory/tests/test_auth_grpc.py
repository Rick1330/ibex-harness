"""Additional coverage for GRPC validator error paths and config."""

from __future__ import annotations

from unittest.mock import AsyncMock, patch
from uuid import UUID

import grpc
import pytest
from authclient import decode_validate_token_response

from app.auth import GRPCTokenValidator, ValidateResult
from app.config import Settings
from app.errors import AuthFailedError, AuthUnavailableError
from app.permissions import MEMORY_READ
from app.principal import Principal, get_principal, set_principal


def test_invalid_transport() -> None:
    with pytest.raises(ValueError):
        Settings(transport="sse")


def test_get_principal_none() -> None:
    set_principal(None)
    assert get_principal() is None
    set_principal(Principal(org_id=UUID(int=1), permissions=MEMORY_READ))
    assert get_principal() is not None
    set_principal(None)


def test_decode_optional_fields() -> None:
    org = "11111111-1111-1111-1111-111111111111"
    org_b = org.encode()
    agent = "22222222-2222-2222-2222-222222222222"
    agent_b = agent.encode()
    user = b"user-1"
    token = b"tok-1"
    payload = b"\x0a" + bytes([len(org_b)]) + org_b
    payload += b"\x10\x07"
    payload += b"\x1a" + bytes([len(agent_b)]) + agent_b
    payload += b"\x22" + bytes([len(user)]) + user
    payload += b"\x2a" + bytes([len(token)]) + token
    got = decode_validate_token_response(payload)
    assert got.agent_id == UUID(agent)
    assert got.user_id == "user-1"
    assert got.token_id == "tok-1"
    assert ValidateResult.from_wire(got).to_principal().agent_id == UUID(agent)


@pytest.mark.asyncio
async def test_grpc_validator_maps_unauthenticated() -> None:
    validator = GRPCTokenValidator("127.0.0.1:9", timeout_seconds=0.01)
    unauth = grpc.aio.AioRpcError(
        code=grpc.StatusCode.UNAUTHENTICATED,
        initial_metadata=(),
        trailing_metadata=(),
        details="nope",
    )
    unavailable = grpc.aio.AioRpcError(
        code=grpc.StatusCode.UNAVAILABLE,
        initial_metadata=(),
        trailing_metadata=(),
        details="down",
    )
    with patch.object(validator, "_stub", new_callable=AsyncMock) as stub:
        stub.side_effect = unauth
        with pytest.raises(AuthFailedError):
            await validator.validate("tok")

        stub.side_effect = unavailable
        with pytest.raises(AuthUnavailableError):
            await validator.validate("tok")

        stub.side_effect = unauth
        assert await validator.ready() is True

        stub.side_effect = unavailable
        assert await validator.ready() is False

        stub.side_effect = None
        org = "11111111-1111-1111-1111-111111111111"
        org_b = org.encode()
        stub.return_value = b"\x0a" + bytes([len(org_b)]) + org_b + b"\x10\x01"
        got = await validator.validate("tok")
        assert got.permissions == 1
    await validator.aclose()


@pytest.mark.asyncio
async def test_grpc_validator_malformed_response_fail_closed() -> None:
    validator = GRPCTokenValidator("127.0.0.1:9", timeout_seconds=0.01)
    with patch.object(validator, "_stub", new_callable=AsyncMock) as stub:
        stub.return_value = b"\xff\xfe\xfd not-a-protobuf"
        with pytest.raises(AuthUnavailableError):
            await validator.validate("tok")
        assert await validator.ready() is False
    await validator.aclose()
