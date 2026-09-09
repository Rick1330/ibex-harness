"""Unit tests for auth gRPC client helpers."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import grpc
import pytest
from authclient import ValidateTokenWire
from authclient.codec import encode_revoke_token_request
from authclient.validate import _map_rpc_error

from app.auth.client import (
    GRPCTokenValidator,
    StaticTokenValidator,
    ValidateResult,
    parse_authorization_header,
)
from app.auth.errors import AuthFailedError, AuthUnavailableError, OrgSuspendedError
from tests.unit.auth_test_support import aio_rpc, patched_validator, wire_bytes


def test_parse_authorization_header_variants() -> None:
    assert parse_authorization_header("bearer tok") == "tok"
    with pytest.raises(AuthFailedError):
        parse_authorization_header(None)
    with pytest.raises(AuthFailedError):
        parse_authorization_header("Basic abc")
    with pytest.raises(AuthFailedError):
        parse_authorization_header("Bearer ")
    with pytest.raises(AuthFailedError, match="maximum length"):
        parse_authorization_header("Bearer " + ("x" * 9000))


def test_validate_result_from_wire() -> None:
    org_id = uuid4()
    agent_id = uuid4()
    wire = ValidateTokenWire(
        org_id=org_id,
        permissions=7,
        agent_id=agent_id,
        user_id="u",
        token_id="t1",
    )
    result = ValidateResult.from_wire(wire)
    assert result.org_id == org_id
    assert result.permissions == 7
    assert result.agent_id == agent_id
    assert result.user_id == "u"
    assert result.token_id == "t1"


@pytest.mark.asyncio
async def test_static_validator_paths() -> None:
    org = uuid4()
    good = ValidateResult(org_id=org, permissions=1)
    v = StaticTokenValidator({"a": good})
    assert await v.validate("a") == good
    with pytest.raises(AuthFailedError):
        await v.validate("b")
    assert await v.ready() is True
    await v.aclose()
    down = StaticTokenValidator({}, available=False)
    with pytest.raises(AuthUnavailableError):
        await down.validate("a")
    assert await down.ready() is False


def test_patched_validator_rejects_untrusted_target() -> None:
    with pytest.raises(ValueError):
        GRPCTokenValidator("evil.example.com:443", timeout_seconds=0.05)


def test_patched_validator_zero_timeout_clamped() -> None:
    with patch("authclient.validate.grpc.aio.insecure_channel") as chan_mock:
        channel = MagicMock()
        channel.unary_unary.return_value = AsyncMock()
        chan_mock.return_value = channel
        validator = GRPCTokenValidator("127.0.0.1:50051", timeout_seconds=0)
        assert validator._timeout == 0.05


@pytest.mark.asyncio
async def test_patched_validator_validate_success() -> None:
    org_id = uuid4()
    wire = ValidateTokenWire(org_id=org_id, permissions=3)
    with patched_validator(return_value=wire_bytes(wire)) as validator:
        result = await validator.validate("tok")
        assert result.org_id == org_id
        assert await validator.ready() is True
        await validator.aclose()


@pytest.mark.asyncio
async def test_patched_validator_unauthenticated() -> None:
    with patched_validator(side_effect=aio_rpc(grpc.StatusCode.UNAUTHENTICATED)) as validator:
        with pytest.raises(AuthFailedError):
            await validator.validate("tok")
        assert await validator.ready() is True
        await validator.aclose()


@pytest.mark.asyncio
async def test_patched_validator_org_suspended() -> None:
    with patched_validator(
        side_effect=aio_rpc(grpc.StatusCode.PERMISSION_DENIED, "organization is suspended")
    ) as validator:
        with pytest.raises(OrgSuspendedError):
            await validator.validate("tok")
        await validator.aclose()


@pytest.mark.asyncio
async def test_patched_validator_unavailable_rpc() -> None:
    with patched_validator(side_effect=aio_rpc(grpc.StatusCode.UNAVAILABLE)) as validator:
        with pytest.raises(AuthUnavailableError):
            await validator.validate("tok")
        assert await validator.ready() is False
        await validator.aclose()


@pytest.mark.asyncio
async def test_patched_validator_os_error() -> None:
    with patched_validator(side_effect=OSError("conn refused")) as validator:
        with pytest.raises(AuthUnavailableError):
            await validator.validate("tok")
        await validator.aclose()


@pytest.mark.asyncio
async def test_patched_validator_bad_response() -> None:
    with patched_validator(return_value="not-bytes") as validator:
        with pytest.raises(AuthUnavailableError, match="not bytes"):
            await validator.validate("tok")
        await validator.aclose()

    bad_payload = bytes([0x10, 0x05])
    with patched_validator(return_value=bad_payload) as validator:
        with pytest.raises(AuthUnavailableError):
            await validator.validate("tok")
        await validator.aclose()


def test_map_rpc_org_suspended() -> None:
    err = _map_rpc_error(aio_rpc(grpc.StatusCode.PERMISSION_DENIED, "organization is suspended"))
    assert isinstance(err, OrgSuspendedError)


def test_encode_revoke_token_request() -> None:
    payload = encode_revoke_token_request(org_id="o", token_id="t", reason="user_deleted")
    assert len(payload) > 0
