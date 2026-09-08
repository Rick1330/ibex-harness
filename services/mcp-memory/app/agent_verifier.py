"""Auth gRPC ValidateAgent client for MCP tool agent-status checks (3.5.F.2)."""

from __future__ import annotations

import asyncio
import logging
from abc import ABC, abstractmethod
from uuid import UUID

import grpc
from authclient import (
    AuthCodecError,
    assert_trusted_insecure_auth_target,
    decode_validate_agent_response,
    encode_validate_agent_request,
)

from app.errors import AuthUnavailableError, PermissionDeniedError

logger = logging.getLogger(__name__)

_VALIDATE_AGENT_METHOD = "/ibex.auth.v1.AuthService/ValidateAgent"
_INACTIVE_MSG = "agent is not active"


class AgentVerifier(ABC):
    @abstractmethod
    async def verify(self, *, bearer: str, org_id: UUID, agent_id: UUID) -> None:
        """Raise PermissionDeniedError when agent is missing, cross-org, or inactive."""

    @abstractmethod
    async def aclose(self) -> None:
        raise NotImplementedError


class GRPCAgentVerifier(AgentVerifier):
    """Bounded ValidateAgent client. Never logs the access token.

    Channel is bound to the running event loop on first use so TestClient
    lifespan/request loop mismatches do not leak cross-loop Futures.
    """

    def __init__(self, target: str, timeout_seconds: float) -> None:
        self._target = assert_trusted_insecure_auth_target(target)
        if timeout_seconds <= 0:
            timeout_seconds = 0.05
        self._timeout = timeout_seconds
        self._channel: grpc.aio.Channel | None = None
        self._stub: object | None = None
        self._loop: asyncio.AbstractEventLoop | None = None

    async def verify(self, *, bearer: str, org_id: UUID, agent_id: UUID) -> None:
        stub = self._ensure_stub()
        metadata = (("authorization", f"Bearer {bearer}"),)
        try:
            payload = await stub(
                (str(agent_id), str(org_id)),
                timeout=self._timeout,
                metadata=metadata,
            )
        except grpc.aio.AioRpcError as exc:
            raise _map_validate_agent_rpc(exc) from exc
        except OSError as exc:
            logger.warning(
                "auth validate_agent unavailable error_class=%s", type(exc).__name__
            )
            raise AuthUnavailableError() from exc
        _require_active_payload(payload)

    async def aclose(self) -> None:
        channel = self._channel
        self._channel = None
        self._stub = None
        self._loop = None
        if channel is not None:
            await channel.close()

    def _ensure_stub(self) -> object:
        loop = asyncio.get_running_loop()
        if self._stub is not None and self._loop is loop:
            return self._stub
        # Drop stale channel from a prior loop (e.g. create_app before TestClient).
        if self._channel is not None:
            close = getattr(self._channel, "close", None)
            if callable(close):
                try:
                    close()
                except Exception:  # noqa: BLE001 — best-effort stale cleanup
                    logger.debug(
                        "stale validate_agent channel close failed", exc_info=True
                    )
        self._channel = grpc.aio.insecure_channel(self._target)
        self._stub = self._channel.unary_unary(
            _VALIDATE_AGENT_METHOD,
            request_serializer=_serialize_request,
            response_deserializer=None,
        )
        self._loop = loop
        return self._stub


class AllowAllAgentVerifier(AgentVerifier):
    """Test helper: every agent is treated as active."""

    async def verify(self, *, bearer: str, org_id: UUID, agent_id: UUID) -> None:
        del bearer, org_id, agent_id

    async def aclose(self) -> None:
        return None


class StaticAgentVerifier(AgentVerifier):
    """Test helper: allow listed (org_id, agent_id) pairs; deny others as inactive."""

    def __init__(
        self,
        allowed: set[tuple[UUID, UUID]] | None = None,
        *,
        deny_message: str = _INACTIVE_MSG,
    ) -> None:
        self._allowed = allowed or set()
        self._deny_message = deny_message

    async def verify(self, *, bearer: str, org_id: UUID, agent_id: UUID) -> None:
        del bearer
        if (org_id, agent_id) not in self._allowed:
            raise PermissionDeniedError(self._deny_message)

    async def aclose(self) -> None:
        return None


def _serialize_request(pair: tuple[str, str]) -> bytes:
    agent_id, org_id = pair
    return encode_validate_agent_request(agent_id=agent_id, org_id=org_id)


def _require_active_payload(payload: object) -> None:
    if not isinstance(payload, (bytes, bytearray)):
        raise AuthUnavailableError("auth response is not bytes")
    try:
        wire = decode_validate_agent_response(bytes(payload))
    except AuthCodecError as exc:
        raise AuthUnavailableError(str(exc)) from exc
    if wire.status != "active":
        raise PermissionDeniedError(_INACTIVE_MSG)


def _map_validate_agent_rpc(
    exc: grpc.aio.AioRpcError,
) -> PermissionDeniedError | AuthUnavailableError:
    if exc.code() == grpc.StatusCode.PERMISSION_DENIED:
        msg = exc.details() or "agent not authorized"
        # Preserve inactive wording for callers; other denials stay permission_denied.
        if _INACTIVE_MSG in msg:
            return PermissionDeniedError(_INACTIVE_MSG)
        return PermissionDeniedError("agent not authorized")
    code_name = exc.code().name if exc.code() is not None else "unknown"
    logger.warning("auth validate_agent fail-closed code=%s", code_name)
    return AuthUnavailableError()
