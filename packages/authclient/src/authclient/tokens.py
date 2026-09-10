"""Async AuthService CreateToken / ListTokens / strict RevokeToken dial clients."""

from __future__ import annotations

import asyncio
import logging
from datetime import UTC, datetime
from typing import Protocol

import grpc

from authclient.codec import (
    AuthCodecError,
    CreateTokenWire,
    ListTokensWire,
    TokenMetadataWire,
    decode_create_token_response,
    decode_list_tokens_response,
    encode_create_token_request,
    encode_list_tokens_request,
    encode_revoke_token_request,
)
from authclient.errors import (
    AuthFailedError,
    AuthUnavailableError,
    InsufficientPermissionsError,
    TokenNotFoundError,
)
from authclient.target import assert_trusted_insecure_auth_target

logger = logging.getLogger(__name__)

_CREATE_METHOD = "/ibex.auth.v1.AuthService/CreateToken"
_LIST_METHOD = "/ibex.auth.v1.AuthService/ListTokens"
_REVOKE_METHOD = "/ibex.auth.v1.AuthService/RevokeToken"


class TokenManager(Protocol):
    """Create / list / strict-revoke tokens via AuthService."""

    async def create(
        self,
        *,
        org_id: str,
        name: str,
        permissions: int,
        access_token: str,
        description: str = "",
        expires_at: datetime | None = None,
        user_id: str | None = None,
        agent_id: str | None = None,
    ) -> CreateTokenWire: ...

    async def list(
        self,
        *,
        org_id: str,
        access_token: str,
        cursor: str = "",
        limit: int = 50,
    ) -> ListTokensWire: ...

    async def revoke_strict(
        self,
        *,
        org_id: str,
        token_id: str,
        access_token: str,
        reason: str | None = None,
    ) -> None: ...

    async def aclose(self) -> None: ...


class GRPCTokenManager:
    """Insecure-channel Create/List/Revoke dial client after trust-gate."""

    def __init__(self, target: str, timeout_seconds: float) -> None:
        trusted = assert_trusted_insecure_auth_target(target)
        timeout = timeout_seconds if timeout_seconds > 0 else 0.05
        self._timeout = timeout
        self._channel = grpc.aio.insecure_channel(trusted)  # nosec B321
        self._create = self._channel.unary_unary(
            _CREATE_METHOD,
            request_serializer=lambda req: req,
            response_deserializer=lambda payload: payload,
        )
        self._list = self._channel.unary_unary(
            _LIST_METHOD,
            request_serializer=lambda req: req,
            response_deserializer=lambda payload: payload,
        )
        self._revoke = self._channel.unary_unary(
            _REVOKE_METHOD,
            request_serializer=lambda req: req,
            response_deserializer=lambda _: None,
        )

    async def create(
        self,
        *,
        org_id: str,
        name: str,
        permissions: int,
        access_token: str,
        description: str = "",
        expires_at: datetime | None = None,
        user_id: str | None = None,
        agent_id: str | None = None,
    ) -> CreateTokenWire:
        payload = encode_create_token_request(
            org_id=org_id,
            name=name,
            permissions=permissions,
            description=description,
            expires_at=expires_at,
            user_id=user_id,
            agent_id=agent_id,
        )
        metadata = (("authorization", f"Bearer {access_token}"),)
        try:
            raw = await self._create(payload, timeout=self._timeout, metadata=metadata)
        except grpc.aio.AioRpcError as exc:
            raise _map_management_rpc(exc, op="create") from exc
        except OSError as exc:
            logger.warning("auth create unavailable error_class=%s", type(exc).__name__)
            raise AuthUnavailableError() from exc
        try:
            if not isinstance(raw, (bytes, bytearray)):
                raise AuthCodecError("create response is not bytes")
            return decode_create_token_response(bytes(raw))
        except AuthCodecError as exc:
            logger.warning("auth create decode failed")
            raise AuthUnavailableError() from exc

    async def list(
        self,
        *,
        org_id: str,
        access_token: str,
        cursor: str = "",
        limit: int = 50,
    ) -> ListTokensWire:
        payload = encode_list_tokens_request(org_id=org_id, cursor=cursor, limit=limit)
        metadata = (("authorization", f"Bearer {access_token}"),)
        try:
            raw = await self._list(payload, timeout=self._timeout, metadata=metadata)
        except grpc.aio.AioRpcError as exc:
            raise _map_management_rpc(exc, op="list") from exc
        except OSError as exc:
            logger.warning("auth list unavailable error_class=%s", type(exc).__name__)
            raise AuthUnavailableError() from exc
        try:
            if not isinstance(raw, (bytes, bytearray)):
                raise AuthCodecError("list response is not bytes")
            return decode_list_tokens_response(bytes(raw))
        except AuthCodecError as exc:
            logger.warning("auth list decode failed")
            raise AuthUnavailableError() from exc

    async def revoke_strict(
        self,
        *,
        org_id: str,
        token_id: str,
        access_token: str,
        reason: str | None = None,
    ) -> None:
        """Revoke one token; NotFound and PermissionDenied surface to callers."""
        payload = encode_revoke_token_request(
            org_id=org_id, token_id=token_id, reason=reason
        )
        metadata = (("authorization", f"Bearer {access_token}"),)
        try:
            await self._revoke(payload, timeout=self._timeout, metadata=metadata)
        except grpc.aio.AioRpcError as exc:
            raise _map_management_rpc(exc, op="revoke") from exc
        except OSError as exc:
            logger.warning("auth revoke unavailable error_class=%s", type(exc).__name__)
            raise AuthUnavailableError() from exc

    async def aclose(self) -> None:
        await self._channel.close()


class FakeTokenManager:
    """In-memory TokenManager for API unit/integration tests."""

    def __init__(self) -> None:
        self.tokens: dict[str, list[TokenMetadataWire]] = {}
        self.created: list[CreateTokenWire] = []
        self.revoked: list[tuple[str, str]] = []
        self.create_error: BaseException | None = None
        self.list_error: BaseException | None = None
        self.revoke_error: BaseException | None = None
        self._seq = 0

    def seed(self, org_id: str, *rows: TokenMetadataWire) -> None:
        self.tokens.setdefault(org_id, []).extend(rows)

    async def create(
        self,
        *,
        org_id: str,
        name: str,
        permissions: int,
        access_token: str,
        description: str = "",
        expires_at: datetime | None = None,
        user_id: str | None = None,
        agent_id: str | None = None,
    ) -> CreateTokenWire:
        del access_token, description, user_id, agent_id
        if self.create_error is not None:
            raise self.create_error
        await asyncio.sleep(0)
        self._seq += 1
        token_id = f"00000000-0000-4000-8000-{self._seq:012d}"
        created = CreateTokenWire(
            token_id=token_id,
            plaintext=f"ibex_pat_{token_id}_secret",
            prefix=f"ibex_pat_{token_id[:8]}",
            created_at=datetime.now(tz=UTC),
        )
        self.created.append(created)
        meta = TokenMetadataWire(
            token_id=token_id,
            name=name,
            prefix=created.prefix,
            permissions=permissions,
            created_at=created.created_at,
            expires_at=expires_at,
        )
        self.tokens.setdefault(org_id, []).append(meta)
        return created

    async def list(
        self,
        *,
        org_id: str,
        access_token: str,
        cursor: str = "",
        limit: int = 50,
    ) -> ListTokensWire:
        del access_token, cursor
        if self.list_error is not None:
            raise self.list_error
        await asyncio.sleep(0)
        rows = list(self.tokens.get(org_id, []))
        if limit <= 0:
            limit = 50
        page = rows[:limit]
        next_cursor = "more" if len(rows) > limit else ""
        return ListTokensWire(tokens=page, next_cursor=next_cursor)

    async def revoke_strict(
        self,
        *,
        org_id: str,
        token_id: str,
        access_token: str,
        reason: str | None = None,
    ) -> None:
        del access_token, reason
        if self.revoke_error is not None:
            raise self.revoke_error
        await asyncio.sleep(0)
        rows = self.tokens.get(org_id, [])
        for i, row in enumerate(rows):
            if row.token_id == token_id:
                rows.pop(i)
                self.revoked.append((org_id, token_id))
                return
        raise TokenNotFoundError()

    async def aclose(self) -> None:
        await asyncio.sleep(0)


def _map_management_rpc(exc: grpc.aio.AioRpcError, *, op: str) -> Exception:
    code = exc.code()
    if code == grpc.StatusCode.UNAUTHENTICATED:
        return AuthFailedError("invalid or revoked token")
    if code == grpc.StatusCode.NOT_FOUND:
        return TokenNotFoundError()
    if code == grpc.StatusCode.PERMISSION_DENIED:
        if op == "create":
            return InsufficientPermissionsError()
        return TokenNotFoundError()
    code_name = code.name if code is not None else "unknown"
    logger.warning("auth %s fail-closed code=%s", op, code_name)
    return AuthUnavailableError()
