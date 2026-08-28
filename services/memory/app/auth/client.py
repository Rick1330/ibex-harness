"""Auth gRPC client for AuthService.ValidateToken."""

from __future__ import annotations

import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass
from uuid import UUID

import grpc
from authclient import (
    MAX_TOKEN_BYTES,
    AuthCodecError,
    ValidateTokenWire,
    assert_trusted_insecure_auth_target,
    decode_validate_token_response,
    encode_validate_token_request,
)

from app.auth.errors import AuthFailedError, AuthUnavailableError

logger = logging.getLogger(__name__)

READINESS_PROBE_SENTINEL = "ibex_health_probe_invalid"
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


class TokenValidator(ABC):
    @abstractmethod
    async def validate(self, access_token: str) -> ValidateResult:
        raise NotImplementedError

    @abstractmethod
    async def ready(self) -> bool:
        raise NotImplementedError

    @abstractmethod
    async def aclose(self) -> None:
        raise NotImplementedError


def parse_authorization_header(header: str | None) -> str:
    if header is None or not header.strip():
        raise AuthFailedError("missing authorization header")
    return _extract_bearer_token(header.strip())


def _extract_bearer_token(header: str) -> str:
    scheme, _, remainder = header.partition(" ")
    if scheme.lower() != "bearer":
        raise AuthFailedError("authorization header must be Bearer <token>")
    token = remainder.strip()
    if not token:
        raise AuthFailedError("authorization header must be Bearer <token>")
    if len(token.encode("utf-8")) > MAX_TOKEN_BYTES:
        raise AuthFailedError("bearer token exceeds maximum length")
    return token


class GRPCTokenValidator(TokenValidator):
    def __init__(self, target: str, timeout_seconds: float) -> None:
        trusted = assert_trusted_insecure_auth_target(target)
        if timeout_seconds <= 0:
            timeout_seconds = 0.05
        self._timeout = timeout_seconds
        self._channel = grpc.aio.insecure_channel(trusted)
        self._stub = self._channel.unary_unary(
            _VALIDATE_METHOD,
            request_serializer=encode_validate_token_request,
            response_deserializer=None,
        )

    async def validate(self, access_token: str) -> ValidateResult:
        try:
            payload = await self._stub(access_token, timeout=self._timeout)
        except grpc.aio.AioRpcError as exc:
            raise _map_rpc_error(exc) from exc
        except OSError as exc:
            logger.warning("auth grpc unavailable error_class=%s", type(exc).__name__)
            raise AuthUnavailableError() from exc
        return _decode_validate_payload(payload)

    async def ready(self) -> bool:
        try:
            await self.validate(READINESS_PROBE_SENTINEL)
            return True
        except AuthFailedError:
            return True
        except AuthUnavailableError:
            return False

    async def aclose(self) -> None:
        await self._channel.close()


def _decode_validate_payload(payload: object) -> ValidateResult:
    if not isinstance(payload, (bytes, bytearray)):
        raise AuthUnavailableError("auth response is not bytes")
    try:
        wire = decode_validate_token_response(bytes(payload))
    except AuthCodecError as exc:
        raise AuthUnavailableError(str(exc)) from exc
    return ValidateResult.from_wire(wire)


def _map_rpc_error(exc: grpc.aio.AioRpcError) -> AuthFailedError | AuthUnavailableError:
    if exc.code() == grpc.StatusCode.UNAUTHENTICATED:
        return AuthFailedError("invalid or revoked token")
    code_name = exc.code().name if exc.code() is not None else "unknown"
    logger.warning("auth grpc fail-closed code=%s", code_name)
    return AuthUnavailableError()


class StaticTokenValidator(TokenValidator):
    """In-memory validator for tests."""

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
