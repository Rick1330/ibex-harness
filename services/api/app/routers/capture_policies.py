"""Capture-policy CRUD routes (4.P.3)."""

from __future__ import annotations

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.client import ValidateResult
from app.authz import RequireOrgSettings, assert_path_org
from app.deps import org_session, require_token
from app.schemas.capture_policies import (
    CapturePolicyCreate,
    CapturePolicyPatch,
    CapturePolicyResponse,
)
from app.services import capture_policies as capture_service

router = APIRouter(prefix="/v1/organizations", tags=["capture-policies"])


@router.get("/{org_id}/capture-policies")
async def list_capture_policies(
    org_id: UUID,
    token: Annotated[ValidateResult, Depends(require_token)],
    session: Annotated[AsyncSession, Depends(org_session)],
) -> list[CapturePolicyResponse]:
    assert_path_org(token.org_id, org_id)
    return await capture_service.list_policies(session, org_id)


@router.get("/{org_id}/capture-policies/resolved")
async def resolve_capture_mode(
    org_id: UUID,
    token: Annotated[ValidateResult, Depends(require_token)],
    session: Annotated[AsyncSession, Depends(org_session)],
    agent_id: UUID | None = None,
) -> dict[str, str]:
    assert_path_org(token.org_id, org_id)
    mode = await capture_service.resolve_mode(session, org_id, agent_id)
    return {"mode": mode}


@router.post("/{org_id}/capture-policies", status_code=status.HTTP_201_CREATED)
async def create_capture_policy(
    org_id: UUID,
    body: CapturePolicyCreate,
    token: RequireOrgSettings,
    session: Annotated[AsyncSession, Depends(org_session)],
) -> CapturePolicyResponse:
    assert_path_org(token.org_id, org_id)
    return await capture_service.create_policy(session, org_id, body)


@router.patch("/{org_id}/capture-policies/{policy_id}")
async def patch_capture_policy(
    org_id: UUID,
    policy_id: UUID,
    body: CapturePolicyPatch,
    token: RequireOrgSettings,
    session: Annotated[AsyncSession, Depends(org_session)],
) -> CapturePolicyResponse:
    assert_path_org(token.org_id, org_id)
    return await capture_service.patch_policy(session, org_id, policy_id, body)


@router.delete("/{org_id}/capture-policies/{policy_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_capture_policy(
    org_id: UUID,
    policy_id: UUID,
    token: RequireOrgSettings,
    session: Annotated[AsyncSession, Depends(org_session)],
) -> None:
    assert_path_org(token.org_id, org_id)
    await capture_service.delete_policy(session, org_id, policy_id)
