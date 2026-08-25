"""Auth gRPC client for AuthService.ValidateToken (fail closed)."""

from __future__ import annotations

import ipaddress
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
READINESS_PROBE_SENTINEL = "ibex_health_probe_invalid"

_VALIDATE_METHOD = "/ibex.auth.v1.AuthService/ValidateToken"
_LOOPBACK_DNS = frozenset({"localhost"})


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
    scheme, _, remainder = header.strip().partition(" ")
    if scheme.lower() != "bearer":
        raise AuthFailedError("authorization header must be Bearer <token>")
    token = remainder.strip()
    if not token:
        raise AuthFailedError("authorization header must be Bearer <token>")
    return token


def assert_trusted_insecure_auth_target(target: str) -> str:
    """Allow insecure gRPC only to loopback, private IP, or mesh short name.

    Public FQDNs must not receive bearer tokens over plaintext gRPC. Compose/k8s
    short names (e.g. ``auth``) are treated as TLS-terminating mesh endpoints.
    """
    cleaned = target.strip()
    if not cleaned:
        raise ValueError("auth gRPC target is required")
    host = _host_of(cleaned)
    if _is_trusted_insecure_host(host):
        return cleaned
    raise ValueError(
        "insecure Auth gRPC requires loopback/private address or mesh short name; "
        f"refusing target host {host!r}"
    )


def _host_of(target: str) -> str:
    cleaned = _strip_grpc_uri_prefix(target.strip())
    bracketed = _host_from_brackets(cleaned)
    if bracketed is not None:
        return bracketed
    return _host_from_hostport(cleaned)


def _strip_grpc_uri_prefix(target: str) -> str:
    lowered = target.lower()
    for prefix in ("dns:///", "dns://", "unix://", "ipv4:", "ipv6:"):
        if lowered.startswith(prefix):
            return target[len(prefix) :]
    return target


def _host_from_brackets(target: str) -> str | None:
    if not target.startswith("["):
        return None
    end = target.find("]")
    if end <= 0:
        return None
    return target[1:end].lower().rstrip(".")


def _host_from_hostport(target: str) -> str:
    host, _, port = target.rpartition(":")
    if host and port.isdigit():
        return host.lower().rstrip(".")
    return target.lower().rstrip(".")


def _is_trusted_insecure_host(host: str) -> bool:
    if not host:
        return False
    if host in _LOOPBACK_DNS:
        return True
    # Compose / k8s short service names (no dots).
    if "." not in host and host.replace("-", "").isalnum():
        return True
    try:
        ip = ipaddress.ip_address(host)
    except ValueError:
        return False
    return bool(ip.is_loopback or ip.is_private)


class GRPCTokenValidator(TokenValidator):
    """Bounded ValidateToken client. Never logs the access token."""

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
        payload = await self._invoke(access_token)
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

    async def _invoke(self, access_token: str) -> bytes:
        try:
            return await self._stub(access_token, timeout=self._timeout)
        except grpc.aio.AioRpcError as exc:
            raise _map_rpc_error(exc) from exc
        except OSError as exc:
            # TimeoutError is an OSError subclass on modern Python.
            logger.warning("auth grpc unavailable error_class=%s", type(exc).__name__)
            raise AuthUnavailableError() from exc


def _decode_validate_payload(payload: object) -> ValidateResult:
    if not isinstance(payload, (bytes, bytearray)):
        raise AuthUnavailableError("auth response is not bytes")
    return ValidateResult.from_wire(decode_validate_token_response(bytes(payload)))


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
