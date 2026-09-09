"""Auth ValidateToken façade over authclient.validate (#779).

Keeps MCP-specific AuthFailedError / AuthUnavailableError (MCPServiceError)
and ValidateResult.to_principal(); dial / codec logic lives in authclient.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from uuid import UUID

import grpc
from authclient import ValidateTokenWire, assert_trusted_insecure_auth_target
from authclient import errors as auth_errors
from authclient import validate as shared

from app.errors import AuthFailedError, AuthUnavailableError
from app.principal import Principal

READINESS_PROBE_SENTINEL = shared.READINESS_PROBE_SENTINEL

__all__ = [
    "READINESS_PROBE_SENTINEL",
    "GRPCTokenValidator",
    "StaticTokenValidator",
    "TokenValidator",
    "ValidateResult",
    "assert_trusted_insecure_auth_target",
    "parse_authorization_header",
]


@dataclass(frozen=True, slots=True)
class ValidateResult:
    org_id: UUID
    permissions: int
    agent_id: UUID | None = None
    user_id: str | None = None
    token_id: str | None = None

    @classmethod
    def from_wire(cls, wire: ValidateTokenWire) -> ValidateResult:
        return cls(
            org_id=wire.org_id,
            permissions=wire.permissions,
            agent_id=wire.agent_id,
            user_id=wire.user_id,
            token_id=wire.token_id,
        )

    @classmethod
    def from_shared(cls, result: shared.ValidateResult) -> ValidateResult:
        return cls(
            org_id=result.org_id,
            permissions=result.permissions,
            agent_id=result.agent_id,
            user_id=result.user_id,
            token_id=result.token_id,
        )

    def to_principal(self) -> Principal:
        return Principal(
            org_id=self.org_id,
            permissions=self.permissions,
            agent_id=self.agent_id,
            user_id=self.user_id,
            token_id=self.token_id,
        )


class TokenValidator(ABC):
    @abstractmethod
    async def validate(self, access_token: str) -> ValidateResult:
        raise NotImplementedError

    @abstractmethod
    async def ready(self) -> bool:
        """True when Auth gRPC answers (Unauthenticated on probe is OK)."""
        raise NotImplementedError

    @abstractmethod
    async def aclose(self) -> None:
        raise NotImplementedError


def parse_authorization_header(header: str | None) -> str:
    try:
        return shared.parse_authorization_header(header)
    except auth_errors.AuthFailedError as exc:
        raise AuthFailedError(str(exc)) from exc


def _map_shared_error(
    exc: auth_errors.AuthFailedError | auth_errors.AuthUnavailableError,
) -> AuthFailedError | AuthUnavailableError:
    if isinstance(exc, auth_errors.AuthFailedError):
        return AuthFailedError(str(exc) or "invalid or revoked token")
    msg = str(exc)
    return AuthUnavailableError(msg) if msg else AuthUnavailableError()


def _map_rpc_error(exc: grpc.aio.AioRpcError) -> AuthFailedError | AuthUnavailableError:
    return _map_shared_error(shared._map_rpc_error(exc))


class GRPCTokenValidator(TokenValidator):
    """Bounded ValidateToken client. Never logs the access token."""

    def __init__(self, target: str, timeout_seconds: float) -> None:
        self._inner = shared.GRPCTokenValidator(target, timeout_seconds)

    async def validate(self, access_token: str) -> ValidateResult:
        try:
            return ValidateResult.from_shared(await self._inner.validate(access_token))
        except (auth_errors.AuthFailedError, auth_errors.AuthUnavailableError) as exc:
            raise _map_shared_error(exc) from exc

    async def ready(self) -> bool:
        return await self._inner.ready()

    async def aclose(self) -> None:
        await self._inner.aclose()


class StaticTokenValidator(TokenValidator):
    """In-memory validator for unit tests (never for production)."""

    def __init__(self, tokens: dict[str, ValidateResult], *, available: bool = True) -> None:
        self._tokens = tokens
        self._available = available

    def set_available(self, available: bool) -> None:
        """Test helper to flip readiness without reconstructing the validator."""
        self._available = available

    async def validate(self, access_token: str) -> ValidateResult:
        if not self._available:
            raise AuthUnavailableError()
        result = self._tokens.get(access_token)
        if result is None:
            raise AuthFailedError("invalid or revoked token")
        return result

    async def ready(self) -> bool:
        return self._available

    async def aclose(self) -> None:
        return None
