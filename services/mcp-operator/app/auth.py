"""Auth ValidateToken façade over authclient.validate.

Returns a ``GatewayPrincipal`` bound solely from the validated token; dial/codec
logic lives in authclient.
"""

from __future__ import annotations

from abc import ABC, abstractmethod

from authclient import errors as auth_errors
from authclient import validate as shared
from mcp_gateway import GatewayPrincipal

from app.errors import AuthFailedError, AuthUnavailableError

READINESS_PROBE_SENTINEL = shared.READINESS_PROBE_SENTINEL

__all__ = [
    "READINESS_PROBE_SENTINEL",
    "GRPCTokenValidator",
    "StaticTokenValidator",
    "TokenValidator",
    "parse_authorization_header",
]


class TokenValidator(ABC):
    @abstractmethod
    async def validate(self, access_token: str) -> GatewayPrincipal:
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


def principal_from_shared(result: shared.ValidateResult) -> GatewayPrincipal:
    return GatewayPrincipal(
        org_id=result.org_id,
        permissions=result.permissions,
        agent_id=result.agent_id,
        principal_id=result.user_id,
        token_id=result.token_id,
    )


class GRPCTokenValidator(TokenValidator):
    """Bounded ValidateToken client. Never logs the access token."""

    def __init__(self, target: str, timeout_seconds: float) -> None:
        self._inner = shared.GRPCTokenValidator(target, timeout_seconds)

    async def validate(self, access_token: str) -> GatewayPrincipal:
        try:
            return principal_from_shared(await self._inner.validate(access_token))
        except (auth_errors.AuthFailedError, auth_errors.AuthUnavailableError) as exc:
            raise _map_shared_error(exc) from exc

    async def ready(self) -> bool:
        return await self._inner.ready()

    async def aclose(self) -> None:
        await self._inner.aclose()


class StaticTokenValidator(TokenValidator):
    """In-memory validator for unit tests (never for production)."""

    def __init__(self, tokens: dict[str, GatewayPrincipal], *, available: bool = True) -> None:
        self._tokens = tokens
        self._available = available

    def set_available(self, available: bool) -> None:
        self._available = available

    async def validate(self, access_token: str) -> GatewayPrincipal:
        if not self._available:
            raise AuthUnavailableError()
        principal = self._tokens.get(access_token)
        if principal is None:
            raise AuthFailedError("invalid or revoked token")
        return principal

    async def ready(self) -> bool:
        return self._available

    async def aclose(self) -> None:
        return None
