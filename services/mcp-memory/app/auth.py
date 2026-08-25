"""Auth gRPC client for AuthService.ValidateToken (fail closed)."""

from __future__ import annotations

import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass
from uuid import UUID

import grpc

from app.errors import AuthFailedError, AuthUnavailableError
from app.principal import Principal
from app.proto_wire import (
    ValidateTokenWire,
    decode_validate_token_response,
    encode_validate_token_request,
)

logger = logging.getLogger(__name__)

# Sentinel rejected at PAT parse without Argon2/Postgres (matches packages/healthcheck).
PROBE_TOKEN = "ibex_health_probe_invalid"

_VALIDATE_METHOD = "/ibex.auth.v1.AuthService/ValidateToken"


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
    if header is None or not header.strip():
        raise AuthFailedError("missing authorization header")
    parts = header.strip().split(None, 1)
    if len(parts) != 2 or parts[0].lower() != "bearer" or not parts[1].strip():
        raise AuthFailedError("authorization header must be Bearer <token>")
    return parts[1].strip()


class GRPCTokenValidator(TokenValidator):
    """Bounded ValidateToken client. Never logs the access token."""

    def __init__(self, target: str, timeout_seconds: float) -> None:
        if not target.strip():
            raise ValueError("auth gRPC target is required")
        if timeout_seconds <= 0:
            timeout_seconds = 0.05
        self._timeout = timeout_seconds
        self._channel = grpc.aio.insecure_channel(target.strip())
        self._stub = self._channel.unary_unary(
            _VALIDATE_METHOD,
            request_serializer=encode_validate_token_request,
            response_deserializer=_deserialize_response,
        )

    async def validate(self, access_token: str) -> ValidateResult:
        try:
            return await self._stub(access_token, timeout=self._timeout)
        except grpc.aio.AioRpcError as exc:
            raise _map_rpc_error(exc) from exc
        except AuthUnavailableError:
            raise
        except (TimeoutError, OSError) as exc:
            logger.warning("auth grpc unavailable error_class=%s", type(exc).__name__)
            raise AuthUnavailableError() from exc

    async def ready(self) -> bool:
        try:
            await self.validate(PROBE_TOKEN)
            return True
        except AuthFailedError:
            return True
        except AuthUnavailableError:
            return False

    async def aclose(self) -> None:
        await self._channel.close()


def _deserialize_response(payload: bytes) -> ValidateResult:
    return ValidateResult.from_wire(decode_validate_token_response(payload))


def _map_rpc_error(exc: grpc.aio.AioRpcError) -> AuthFailedError | AuthUnavailableError:
    if exc.code() == grpc.StatusCode.UNAUTHENTICATED:
        return AuthFailedError("invalid or revoked token")
    code_name = exc.code().name if exc.code() is not None else "unknown"
    logger.warning("auth grpc fail-closed code=%s", code_name)
    return AuthUnavailableError()


class StaticTokenValidator(TokenValidator):
    """In-memory validator for unit tests (never for production)."""

    def __init__(self, tokens: dict[str, ValidateResult], *, available: bool = True) -> None:
        self._tokens = tokens
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
