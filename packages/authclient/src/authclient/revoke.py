"""Async AuthService.RevokeToken dial client."""

from __future__ import annotations

import asyncio
import logging

import grpc

from authclient.channel import open_auth_channel
from authclient.codec import encode_revoke_token_request
from authclient.errors import AuthFailedError, AuthUnavailableError

logger = logging.getLogger(__name__)

_REVOKE_METHOD = "/ibex.auth.v1.AuthService/RevokeToken"


class GRPCTokenRevoker:
    """RevokeToken client: TLS when a CA file is set, else the trust-gated insecure dial."""

    def __init__(self, target: str, timeout_seconds: float, ca_file: str | None = None) -> None:
        timeout = timeout_seconds if timeout_seconds > 0 else 0.05
        self._timeout = timeout
        # Transport choice and the plaintext trust gate both live in the factory.
        self._channel = open_auth_channel(target, ca_file)
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
            if exc.code() == grpc.StatusCode.NOT_FOUND:
                # Already-revoked / unknown token: treat as success for delete loops.
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
        await asyncio.sleep(0)
        self.calls.append((org_id, token_id))

    async def aclose(self) -> None:
        await asyncio.sleep(0)
