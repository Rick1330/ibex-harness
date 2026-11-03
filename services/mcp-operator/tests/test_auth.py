"""Auth façade: header parsing, principal binding, static validator."""

from __future__ import annotations

import pytest
from authclient import errors as auth_errors
from authclient.validate import ValidateResult
from mcp_gateway import GatewayPrincipal

from app.auth import (
    parse_authorization_header,
    principal_from_shared,
)
from app.errors import AuthFailedError, AuthUnavailableError
from tests.fixtures import AGENT, ORG, TOKEN_A, static_validator


def test_parse_authorization_header_ok() -> None:
    assert parse_authorization_header("Bearer abc") == "abc"


@pytest.mark.parametrize("header", [None, "", "Token abc", "Bearer "])
def test_parse_authorization_header_rejects(header: str | None) -> None:
    with pytest.raises(AuthFailedError):
        parse_authorization_header(header)


def test_principal_from_shared_maps_user_id() -> None:
    shared = ValidateResult(org_id=ORG, permissions=7, agent_id=AGENT, user_id="user-1")
    principal = principal_from_shared(shared)
    assert principal == GatewayPrincipal(
        org_id=ORG, permissions=7, agent_id=AGENT, principal_id="user-1"
    )


@pytest.mark.asyncio
async def test_static_validator_roundtrip() -> None:
    validator = static_validator()
    principal = await validator.validate(TOKEN_A)
    assert principal.org_id == ORG
    assert await validator.ready() is True


@pytest.mark.asyncio
async def test_static_validator_rejects_unknown_token() -> None:
    validator = static_validator()
    with pytest.raises(AuthFailedError):
        await validator.validate("nope")


@pytest.mark.asyncio
async def test_static_validator_unavailable_fails_closed() -> None:
    validator = static_validator(available=False)
    with pytest.raises(AuthUnavailableError):
        await validator.validate(TOKEN_A)
    assert await validator.ready() is False


def test_authclient_error_hierarchy_is_expected() -> None:
    # Guard against authclient error-type drift the façade maps.
    assert issubclass(auth_errors.OrgSuspendedError, auth_errors.AuthFailedError)


@pytest.mark.asyncio
async def test_grpc_validator_maps_shared_errors(monkeypatch: pytest.MonkeyPatch) -> None:
    from app import auth as auth_mod

    class _FakeInner:
        def __init__(self, target: str, timeout_seconds: float) -> None:
            self.result: object = ValidateResult(org_id=ORG, permissions=3)
            self.error: Exception | None = None
            self.ready_value = True
            self.closed = False

        async def validate(self, _token: str) -> object:
            if self.error is not None:
                raise self.error
            return self.result

        async def ready(self) -> bool:
            return self.ready_value

        async def aclose(self) -> None:
            self.closed = True

    monkeypatch.setattr(auth_mod.shared, "GRPCTokenValidator", _FakeInner)
    validator = auth_mod.GRPCTokenValidator("127.0.0.1:1", 0.05)

    principal = await validator.validate("tok")
    assert principal.org_id == ORG
    assert await validator.ready() is True

    validator._inner.error = auth_errors.AuthFailedError("bad")
    with pytest.raises(AuthFailedError):
        await validator.validate("tok")

    validator._inner.error = auth_errors.AuthUnavailableError("down")
    with pytest.raises(AuthUnavailableError):
        await validator.validate("tok")

    await validator.aclose()
    assert validator._inner.closed is True
