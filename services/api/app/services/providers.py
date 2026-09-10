"""Provider credential orchestration over AuthService gRPC."""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from uuid import UUID

from apierror_py import (
    AUTH_UNAVAILABLE,
    INSUFFICIENT_PERMISSIONS,
    INVALID_TOKEN,
    NOT_FOUND,
)
from authclient.errors import (
    AuthFailedError,
    AuthUnavailableError,
    InsufficientPermissionsError,
    ProviderCredentialNotFoundError,
)
from authclient.provider_credentials import (
    CreateProviderCredentialParams,
    ProviderCredentialManager,
    ProviderCredentialMetadataWire,
)

from app.auth.client import ValidateResult
from app.errors import ApiError
from app.schemas.providers import (
    ProviderCredentialListResponse,
    ProviderCredentialResponse,
    ProviderCredentialUpsertRequest,
)
from app.services import provider_validate

CREDENTIAL_NOT_FOUND_MSG = "Provider credential not found"


@dataclass(frozen=True, slots=True)
class ProviderCredentialAccess:
    token: ValidateResult
    access_token: str
    manager: ProviderCredentialManager


def _meta_to_response(row: ProviderCredentialMetadataWire) -> ProviderCredentialResponse:
    return ProviderCredentialResponse(
        provider_name=row.provider_name,
        status=row.status,
        key_hint=row.key_hint,
        base_url=row.base_url or None,
        last_validated_at=row.last_validated_at,
    )


def _map_cred_rpc(exc: BaseException) -> ApiError:
    if isinstance(exc, ProviderCredentialNotFoundError):
        return ApiError(code=NOT_FOUND, message=CREDENTIAL_NOT_FOUND_MSG)
    if isinstance(exc, InsufficientPermissionsError):
        return ApiError(code=INSUFFICIENT_PERMISSIONS, message="Insufficient permissions")
    if isinstance(exc, AuthFailedError):
        return ApiError(code=INVALID_TOKEN, message="Invalid token")
    if isinstance(exc, AuthUnavailableError):
        return ApiError(code=AUTH_UNAVAILABLE, message="Auth service unavailable")
    return ApiError(code=AUTH_UNAVAILABLE, message="Auth service unavailable")


async def _call_auth[T](op: Callable[[], Awaitable[T]]) -> T:
    try:
        return await op()
    except (
        ProviderCredentialNotFoundError,
        InsufficientPermissionsError,
        AuthFailedError,
        AuthUnavailableError,
    ) as exc:
        raise _map_cred_rpc(exc) from exc


async def list_provider_credentials(
    access: ProviderCredentialAccess,
    org_id: UUID,
) -> ProviderCredentialListResponse:
    wire = await _call_auth(
        lambda: access.manager.list(
            org_id=str(org_id),
            access_token=access.access_token,
        )
    )
    return ProviderCredentialListResponse(
        credentials=[_meta_to_response(row) for row in wire.credentials]
    )


async def upsert_provider_credential(
    access: ProviderCredentialAccess,
    org_id: UUID,
    body: ProviderCredentialUpsertRequest,
) -> ProviderCredentialResponse:
    await provider_validate.validate_provider_credential(
        provider_name=body.provider_name,
        api_key=body.api_key,
        base_url=body.base_url,
    )
    meta = await _call_auth(
        lambda: access.manager.create(
            CreateProviderCredentialParams(
                org_id=str(org_id),
                provider_name=body.provider_name,
                api_key=body.api_key,
                access_token=access.access_token,
                base_url=body.base_url or "",
            )
        )
    )
    return _meta_to_response(meta)


async def delete_provider_credential(
    access: ProviderCredentialAccess,
    org_id: UUID,
    provider_name: str,
) -> None:
    await _call_auth(
        lambda: access.manager.delete(
            org_id=str(org_id),
            provider_name=provider_name,
            access_token=access.access_token,
        )
    )
