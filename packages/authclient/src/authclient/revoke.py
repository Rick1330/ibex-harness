"""Async AuthService.RevokeToken dial client."""

from __future__ import annotations

import logging

import grpc

from authclient.codec import encode_revoke_token_request
from authclient.errors import AuthFailedError, AuthUnavailableError
from authclient.target import assert_trusted_insecure_auth_target

logger = logging.getLogger(__name__)

_REVOKE_METHOD = "/ibex.auth.v1.AuthService/RevokeToken"


class GRPCTokenRevoker:
    """Insecure-channel RevokeToken client after trust-gate on the target."""

    def __init__(self, target: str, timeout_seconds: float) -> None:
        trusted = assert_trusted_insecure_auth_target(target)
        timeout = timeout_seconds if timeout_seconds > 0 else 0.05
        self._timeout = timeout
        self._channel = grpc.aio.insecure_channel(trusted)  # nosec B321
        self._stub = self._channel.unary_unary(
            _REVOKE_METHOD,
            request_serializer=lambda req: req,
            response_deserializer=lambda _: None,
        )

    async def revoke(
        self,
        *,
        org_id: str,
        token_id: str,
        access_token: str,
        reason: str | None = None,
    ) -> None:
        payload = encode_revoke_token_request(
            org_id=org_id, token_id=token_id, reason=reason
        )
        metadata = (("authorization", f"Bearer {access_token}"),)
        try:
            await self._stub(payload, timeout=self._timeout, metadata=metadata)
        except grpc.aio.AioRpcError as exc:
            if exc.code() in (
                grpc.StatusCode.NOT_FOUND,
                grpc.StatusCode.PERMISSION_DENIED,
            ):
                # Anti-enumeration / already-revoked: treat as success for delete loops.
                return
            if exc.code() == grpc.StatusCode.UNAUTHENTICATED:
                raise AuthFailedError("invalid or revoked token") from exc
            code_name = exc.code().name if exc.code() is not None else "unknown"
            logger.warning("auth revoke fail-closed code=%s", code_name)
            raise AuthUnavailableError() from exc
        except OSError as exc:
            logger.warning("auth revoke unavailable error_class=%s", type(exc).__name__)
            raise AuthUnavailableError() from exc

    async def aclose(self) -> None:
        await self._channel.close()


class NoopTokenRevoker:
    """Test double that records revoke calls."""

    def __init__(self) -> None:
        self.calls: list[tuple[str, str]] = []

    async def revoke(
        self,
        *,
        org_id: str,
        token_id: str,
        access_token: str,
        reason: str | None = None,
    ) -> None:
        del access_token, reason
        self.calls.append((org_id, token_id))

    async def aclose(self) -> None:
        return None
