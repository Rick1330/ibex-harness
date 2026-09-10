"""Org-scoped provider credential routes (AuthService gRPC façade)."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Header, Request, Response, status

from app.auth.client import parse_authorization_header
from app.authz import RequireOrgSettings, assert_path_org
from app.schemas.providers import (
    ProviderCredentialListResponse,
    ProviderCredentialResponse,
    ProviderCredentialUpsertRequest,
)
from app.services import providers as provider_service
from app.services.providers import ProviderCredentialAccess

router = APIRouter(prefix="/v1/organizations", tags=["providers"])


def _bearer_token(
    authorization: Annotated[str | None, Header(alias="Authorization")] = None,
) -> str:
    return parse_authorization_header(authorization)


@dataclass(frozen=True)
class _ProviderCtx:
    access: ProviderCredentialAccess
    org_id: UUID


def _provider_ctx(
    request: Request,
    org_id: UUID,
    token: RequireOrgSettings,
    access_token: Annotated[str, Depends(_bearer_token)],
) -> _ProviderCtx:
    assert_path_org(token.org_id, org_id)
    manager = request.app.state.api.provider_credential_manager
    return _ProviderCtx(
        access=ProviderCredentialAccess(
            token=token, access_token=access_token, manager=manager
        ),
        org_id=org_id,
    )


@router.get("/{org_id}/providers")
async def list_providers(
    ctx: Annotated[_ProviderCtx, Depends(_provider_ctx)],
) -> ProviderCredentialListResponse:
    return await provider_service.list_provider_credentials(ctx.access, ctx.org_id)


@router.post("/{org_id}/providers", status_code=status.HTTP_201_CREATED)
async def upsert_provider(
    body: ProviderCredentialUpsertRequest,
    ctx: Annotated[_ProviderCtx, Depends(_provider_ctx)],
) -> ProviderCredentialResponse:
    return await provider_service.upsert_provider_credential(ctx.access, ctx.org_id, body)


@router.delete("/{org_id}/providers/{provider_name}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_provider(
    provider_name: str,
    ctx: Annotated[_ProviderCtx, Depends(_provider_ctx)],
) -> Response:
    await provider_service.delete_provider_credential(
        ctx.access, ctx.org_id, provider_name
    )
    return Response(status_code=status.HTTP_204_NO_CONTENT)
