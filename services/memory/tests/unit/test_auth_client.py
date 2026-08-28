"""Unit tests for auth gRPC client helpers."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import grpc
import pytest

from app.auth.client import (
    GRPCTokenValidator,
    StaticTokenValidator,
    ValidateResult,
    assert_trusted_insecure_auth_target,
    parse_authorization_header,
)
from app.auth.errors import AuthFailedError, AuthUnavailableError
from app.auth.proto_wire import ValidateTokenWire
from tests.unit.auth_test_support import encode_validate_token_wire, grpc_validator, rpc_error


def test_parse_authorization_header_bearer_case_insensitive() -> None:
    assert parse_authorization_header("bearer tok") == "tok"


def test_parse_authorization_header_wrong_scheme() -> None:
    with pytest.raises(AuthFailedError, match="Bearer"):
        parse_authorization_header("Basic abc")


def test_parse_authorization_header_empty_token() -> None:
    with pytest.raises(AuthFailedError):
        parse_authorization_header("Bearer   ")


def test_parse_authorization_header_rejects_oversized_token() -> None:
    with pytest.raises(AuthFailedError, match="maximum length"):
        parse_authorization_header("Bearer " + ("x" * 9000))


def test_assert_trusted_loopback() -> None:
    assert assert_trusted_insecure_auth_target("127.0.0.1:50051") == "127.0.0.1:50051"
    assert assert_trusted_insecure_auth_target("localhost:50051") == "localhost:50051"


def test_assert_trusted_mesh_short_name() -> None:
    assert assert_trusted_insecure_auth_target("auth:50051") == "auth:50051"


def test_assert_trusted_private_ip() -> None:
    assert assert_trusted_insecure_auth_target("10.0.0.5:50051") == "10.0.0.5:50051"


def test_assert_trusted_ipv6_loopback() -> None:
    assert assert_trusted_insecure_auth_target("[::1]:50051") == "[::1]:50051"


def test_assert_trusted_dns_prefix() -> None:
    assert assert_trusted_insecure_auth_target("dns:///127.0.0.1:50051") == "dns:///127.0.0.1:50051"


def test_assert_trusted_rejects_public_host() -> None:
    with pytest.raises(ValueError, match="refusing target"):
        assert_trusted_insecure_auth_target("evil.example.com:50051")


def test_assert_trusted_empty_target() -> None:
    with pytest.raises(ValueError, match="required"):
        assert_trusted_insecure_auth_target("  ")


def test_validate_result_from_wire() -> None:
    org_id = uuid4()
    agent_id = uuid4()
    wire = ValidateTokenWire(org_id=org_id, permissions=7, agent_id=agent_id, user_id="u")
    result = ValidateResult.from_wire(wire)
    assert result.org_id == org_id
    assert result.permissions == 7
    assert result.agent_id == agent_id
    assert result.user_id == "u"


@pytest.mark.asyncio
async def test_static_validator_invalid_token() -> None:
    validator = StaticTokenValidator({})
    with pytest.raises(AuthFailedError):
        await validator.validate("missing")


@pytest.mark.asyncio
async def test_static_validator_ready() -> None:
    validator = StaticTokenValidator({}, available=True)
    assert await validator.ready() is True
    validator2 = StaticTokenValidator({}, available=False)
    assert await validator2.ready() is False


@pytest.mark.asyncio
async def test_grpc_validator_validate_success() -> None:
    org_id = uuid4()
    wire = ValidateTokenWire(org_id=org_id, permissions=3)
    with grpc_validator(return_value=encode_validate_token_wire(wire)) as validator:
        result = await validator.validate("tok")
        assert result.org_id == org_id
        await validator.aclose()


@pytest.mark.asyncio
async def test_grpc_validator_unauthenticated() -> None:
    with grpc_validator(side_effect=rpc_error(grpc.StatusCode.UNAUTHENTICATED)) as validator:
        with pytest.raises(AuthFailedError):
            await validator.validate("tok")
        await validator.aclose()


@pytest.mark.asyncio
async def test_grpc_validator_unavailable_rpc() -> None:
    with grpc_validator(side_effect=rpc_error(grpc.StatusCode.UNAVAILABLE)) as validator:
        with pytest.raises(AuthUnavailableError):
            await validator.validate("tok")
        await validator.aclose()


@pytest.mark.asyncio
async def test_grpc_validator_os_error() -> None:
    with grpc_validator(side_effect=OSError("conn refused")) as validator:
        with pytest.raises(AuthUnavailableError):
            await validator.validate("tok")
        await validator.aclose()


@pytest.mark.asyncio
async def test_grpc_validator_bad_response_type() -> None:
    with grpc_validator(return_value="not-bytes") as validator:
        with pytest.raises(AuthUnavailableError, match="not bytes"):
            await validator.validate("tok")
        await validator.aclose()


@pytest.mark.asyncio
async def test_grpc_validator_ready_probe() -> None:
    with grpc_validator(side_effect=rpc_error(grpc.StatusCode.UNAUTHENTICATED)) as validator:
        assert await validator.ready() is True
        await validator.aclose()


@pytest.mark.asyncio
async def test_grpc_validator_ready_unavailable() -> None:
    with grpc_validator(side_effect=OSError("down")) as validator:
        assert await validator.ready() is False
        await validator.aclose()


def test_grpc_validator_zero_timeout_clamped() -> None:
    with patch("app.auth.client.grpc.aio.insecure_channel") as chan_mock:
        channel = MagicMock()
        channel.unary_unary.return_value = AsyncMock()
        chan_mock.return_value = channel
        validator = GRPCTokenValidator("127.0.0.1:50051", timeout_seconds=0)
        assert validator._timeout == 0.05
