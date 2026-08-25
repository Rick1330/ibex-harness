"""Unit tests for auth header parsing and static validator."""

from __future__ import annotations

from uuid import UUID

import pytest

from app.auth import StaticTokenValidator, ValidateResult, parse_authorization_header
from app.errors import AuthFailedError, AuthUnavailableError

ORG = UUID("11111111-1111-1111-1111-111111111111")


def test_parse_authorization_header_ok() -> None:
    assert parse_authorization_header("Bearer tok-1") == "tok-1"


def test_parse_authorization_header_missing() -> None:
    with pytest.raises(AuthFailedError):
        parse_authorization_header(None)
    with pytest.raises(AuthFailedError):
        parse_authorization_header("Basic x")


@pytest.mark.asyncio
async def test_static_validator_maps_tokens() -> None:
    validator = StaticTokenValidator(
        {
            "good": ValidateResult(org_id=ORG, permissions=3),
        }
    )
    got = await validator.validate("good")
    assert got.org_id == ORG
    assert got.permissions == 3
    with pytest.raises(AuthFailedError):
        await validator.validate("bad")
    assert await validator.ready() is True


@pytest.mark.asyncio
async def test_static_validator_unavailable() -> None:
    validator = StaticTokenValidator({}, available=False)
    with pytest.raises(AuthUnavailableError):
        await validator.validate("any")
    assert await validator.ready() is False


def test_map_rpc_unauthenticated() -> None:
    from unittest.mock import MagicMock

    import grpc

    from app.auth import _map_rpc_error

    exc = MagicMock()
    exc.code.return_value = grpc.StatusCode.UNAUTHENTICATED
    err = _map_rpc_error(exc)
    assert isinstance(err, AuthFailedError)


def test_map_rpc_unavailable() -> None:
    from unittest.mock import MagicMock

    import grpc

    from app.auth import _map_rpc_error

    exc = MagicMock()
    exc.code.return_value = grpc.StatusCode.UNAVAILABLE
    err = _map_rpc_error(exc)
    assert isinstance(err, AuthUnavailableError)
