"""Async AuthService provider-credential dial clients."""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Protocol

import grpc

from authclient.codec import (
    AuthCodecError,
    CreateProviderCredentialEncodeFields,
    GetProviderCredentialWire,
    ListProviderCredentialsWire,
    ProviderCredentialMetadataWire,
    decode_create_provider_credential_response,
    decode_get_provider_credential_response,
    decode_list_provider_credentials_response,
    encode_create_provider_credential_request,
    encode_delete_provider_credential_request,
    encode_get_provider_credential_request,
    encode_list_provider_credentials_request,
)
from authclient.errors import (
    AuthFailedError,
    AuthUnavailableError,
    InsufficientPermissionsError,
    ProviderCredentialNotFoundError,
)
from authclient.target import assert_trusted_insecure_auth_target

logger = logging.getLogger(__name__)

_CREATE_METHOD = "/ibex.auth.v1.AuthService/CreateProviderCredential"
_GET_METHOD = "/ibex.auth.v1.AuthService/GetProviderCredential"
_LIST_METHOD = "/ibex.auth.v1.AuthService/ListProviderCredentials"
_DELETE_METHOD = "/ibex.auth.v1.AuthService/DeleteProviderCredential"


@dataclass(frozen=True, slots=True)
class CreateProviderCredentialParams:
    org_id: str
    provider_name: str
    api_key: str
    access_token: str
    base_url: str = ""


@dataclass(frozen=True, slots=True)
class _UnaryBytesCall[T]:
    stub: Callable[..., Awaitable[object]]
    payload: bytes
    access_token: str
    op: str
    decode: Callable[[bytes], T]


class ProviderCredentialManager(Protocol):
    async def create(
        self, params: CreateProviderCredentialParams
    ) -> ProviderCredentialMetadataWire: ...

    async def get(
        self, *, org_id: str, provider_name: str, access_token: str
    ) -> GetProviderCredentialWire: ...

    async def list(
        self, *, org_id: str, access_token: str
    ) -> ListProviderCredentialsWire: ...

    async def delete(
        self, *, org_id: str, provider_name: str, access_token: str
    ) -> None: ...

    async def aclose(self) -> None: ...


class GRPCProviderCredentialManager:
    """Create/Get/List/Delete dial client after the shared insecure-target trust gate."""

    def __init__(self, target: str, timeout_seconds: float) -> None:
        trusted = assert_trusted_insecure_auth_target(target)
        timeout = timeout_seconds if timeout_seconds > 0 else 0.05
        self._timeout = timeout
        # nosec B321 — same trust-gated insecure dial as token management.
        self._channel = grpc.aio.insecure_channel(trusted)
        self._create = self._channel.unary_unary(
            _CREATE_METHOD,
            request_serializer=lambda req: req,
            response_deserializer=lambda payload: payload,
        )
        self._get = self._channel.unary_unary(
            _GET_METHOD,
            request_serializer=lambda req: req,
            response_deserializer=lambda payload: payload,
        )
        self._list = self._channel.unary_unary(
            _LIST_METHOD,
            request_serializer=lambda req: req,
            response_deserializer=lambda payload: payload,
        )
        self._delete = self._channel.unary_unary(
            _DELETE_METHOD,
            request_serializer=lambda req: req,
            response_deserializer=lambda _: None,
        )

    async def create(
        self, params: CreateProviderCredentialParams
    ) -> ProviderCredentialMetadataWire:
        payload = encode_create_provider_credential_request(
            CreateProviderCredentialEncodeFields(
                org_id=params.org_id,
                provider_name=params.provider_name,
                api_key=params.api_key,
                base_url=params.base_url,
            )
        )
        return await self._unary_bytes(
            _UnaryBytesCall(
                stub=self._create,
                payload=payload,
                access_token=params.access_token,
                op="create",
                decode=decode_create_provider_credential_response,
            )
        )

    async def get(
        self, *, org_id: str, provider_name: str, access_token: str
    ) -> GetProviderCredentialWire:
        return await self._unary_bytes(
            _UnaryBytesCall(
                stub=self._get,
                payload=encode_get_provider_credential_request(
                    org_id=org_id, provider_name=provider_name
                ),
                access_token=access_token,
                op="get",
                decode=decode_get_provider_credential_response,
            )
        )

    async def list(
        self, *, org_id: str, access_token: str
    ) -> ListProviderCredentialsWire:
        return await self._unary_bytes(
            _UnaryBytesCall(
                stub=self._list,
                payload=encode_list_provider_credentials_request(org_id=org_id),
                access_token=access_token,
                op="list",
                decode=decode_list_provider_credentials_response,
            )
        )

    async def delete(
        self, *, org_id: str, provider_name: str, access_token: str
    ) -> None:
        await self._unary_bytes(
            _UnaryBytesCall(
                stub=self._delete,
                payload=encode_delete_provider_credential_request(
                    org_id=org_id, provider_name=provider_name
                ),
                access_token=access_token,
                op="delete",
                decode=_decode_empty,
            )
        )

    async def aclose(self) -> None:
        await self._channel.close()

    async def _unary_bytes[T](self, call: _UnaryBytesCall[T]) -> T:
        metadata = (("authorization", f"Bearer {call.access_token}"),)
        try:
            raw = await call.stub(
                call.payload, timeout=self._timeout, metadata=metadata
            )
        except grpc.aio.AioRpcError as exc:
            raise _map_cred_rpc(exc, op=call.op) from exc
        except OSError as exc:
            logger.warning(
                "auth %s unavailable error_class=%s", call.op, type(exc).__name__
            )
            raise AuthUnavailableError() from exc
        return _decode_unary_payload(call.op, call.decode, raw)


class FakeProviderCredentialManager:
    """In-memory ProviderCredentialManager for API unit/integration tests."""

    def __init__(self) -> None:
        self.rows: dict[tuple[str, str], ProviderCredentialMetadataWire] = {}
        self.secrets: dict[tuple[str, str], str] = {}
        self.created: list[ProviderCredentialMetadataWire] = []
        self.deleted: list[tuple[str, str]] = []
        self.create_error: BaseException | None = None
        self.get_error: BaseException | None = None
        self.list_error: BaseException | None = None
        self.delete_error: BaseException | None = None

    def seed(
        self,
        org_id: str,
        row: ProviderCredentialMetadataWire,
        *,
        api_key: str = "sk-test",
    ) -> None:
        key = (org_id, row.provider_name)
        self.rows[key] = row
        self.secrets[key] = api_key

    async def create(
        self, params: CreateProviderCredentialParams
    ) -> ProviderCredentialMetadataWire:
        if self.create_error is not None:
            raise self.create_error
        await asyncio.sleep(0)
        hint = (
            params.api_key[-4:]
            if len(params.api_key) >= 5
            else "[REDACTED]"
        )
        meta = ProviderCredentialMetadataWire(
            provider_name=params.provider_name,
            status="active",
            key_hint=hint,
            base_url=params.base_url,
            encryption_key_id="v1",
            last_validated_at=datetime.now(tz=UTC),
        )
        key = (params.org_id, params.provider_name)
        self.rows[key] = meta
        self.secrets[key] = params.api_key
        self.created.append(meta)
        return meta

    async def get(
        self, *, org_id: str, provider_name: str, access_token: str
    ) -> GetProviderCredentialWire:
        del access_token
        if self.get_error is not None:
            raise self.get_error
        await asyncio.sleep(0)
        key = (org_id, provider_name)
        if key not in self.rows:
            return GetProviderCredentialWire(is_platform_default=True)
        return GetProviderCredentialWire(
            api_key=self.secrets.get(key, ""),
            base_url=self.rows[key].base_url,
            is_platform_default=False,
        )

    async def list(
        self, *, org_id: str, access_token: str
    ) -> ListProviderCredentialsWire:
        del access_token
        if self.list_error is not None:
            raise self.list_error
        await asyncio.sleep(0)
        rows = [row for (oid, _), row in self.rows.items() if oid == org_id]
        return ListProviderCredentialsWire(credentials=rows)

    async def delete(
        self, *, org_id: str, provider_name: str, access_token: str
    ) -> None:
        del access_token
        if self.delete_error is not None:
            raise self.delete_error
        await asyncio.sleep(0)
        key = (org_id, provider_name)
        if key not in self.rows:
            raise ProviderCredentialNotFoundError()
        del self.rows[key]
        self.secrets.pop(key, None)
        self.deleted.append(key)

    async def aclose(self) -> None:
        await asyncio.sleep(0)


_CredRpcError = (
    AuthFailedError
    | ProviderCredentialNotFoundError
    | InsufficientPermissionsError
    | AuthUnavailableError
)


def _decode_empty(raw: bytes) -> None:
    del raw


def _decode_unary_payload[T](
    op: str, decode: Callable[[bytes], T], raw: object
) -> T:
    try:
        if raw is None:
            return decode(b"")
        if not isinstance(raw, (bytes, bytearray)):
            raise AuthCodecError(f"{op} response is not bytes")
        return decode(bytes(raw))
    except AuthCodecError as exc:
        logger.warning("auth %s decode failed", op)
        raise AuthUnavailableError() from exc


def _map_cred_rpc(exc: grpc.aio.AioRpcError, *, op: str) -> _CredRpcError:
    code = exc.code()
    if code == grpc.StatusCode.UNAUTHENTICATED:
        return AuthFailedError("invalid or revoked token")
    if code == grpc.StatusCode.NOT_FOUND:
        return ProviderCredentialNotFoundError()
    if code == grpc.StatusCode.PERMISSION_DENIED:
        if op in {"create", "list"}:
            return InsufficientPermissionsError()
        return ProviderCredentialNotFoundError()
    code_name = code.name if code is not None else "unknown"
    logger.warning("auth %s fail-closed code=%s", op, code_name)
    return AuthUnavailableError()
