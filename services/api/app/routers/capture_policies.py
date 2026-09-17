"""Capture-policy CRUD routes (4.P.3)."""

from __future__ import annotations

from dataclasses import dataclass
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


@dataclass(frozen=True, slots=True)
class _Ctx:
    org_id: UUID
    session: AsyncSession


def _make_ctx(org_id: UUID, token_org_id: UUID, session: AsyncSession) -> _Ctx:
    assert_path_org(token_org_id, org_id)
    return _Ctx(org_id=org_id, session=session)


def _read_ctx(
    org_id: UUID,
    token: Annotated[ValidateResult, Depends(require_token)],
    session: Annotated[AsyncSession, Depends(org_session)],
) -> _Ctx:
    return _make_ctx(org_id, token.org_id, session)


def _write_ctx(
    org_id: UUID,
    token: RequireOrgSettings,
    session: Annotated[AsyncSession, Depends(org_session)],
) -> _Ctx:
    return _make_ctx(org_id, token.org_id, session)


@router.get("/{org_id}/capture-policies")
async def list_capture_policies(
    ctx: Annotated[_Ctx, Depends(_read_ctx)],
) -> list[CapturePolicyResponse]:
    return await capture_service.list_policies(ctx.session, ctx.org_id)


@router.get("/{org_id}/capture-policies/resolved")
async def resolve_capture_mode(
    ctx: Annotated[_Ctx, Depends(_read_ctx)],
    agent_id: UUID | None = None,
) -> dict[str, str]:
    mode = await capture_service.resolve_mode(ctx.session, ctx.org_id, agent_id)
    return {"mode": mode}


@router.post("/{org_id}/capture-policies", status_code=status.HTTP_201_CREATED)
async def create_capture_policy(
    body: CapturePolicyCreate,
    ctx: Annotated[_Ctx, Depends(_write_ctx)],
) -> CapturePolicyResponse:
    return await capture_service.create_policy(ctx.session, ctx.org_id, body)


@router.patch("/{org_id}/capture-policies/{policy_id}")
async def patch_capture_policy(
    policy_id: UUID,
    body: CapturePolicyPatch,
    ctx: Annotated[_Ctx, Depends(_write_ctx)],
) -> CapturePolicyResponse:
    return await capture_service.patch_policy(ctx.session, ctx.org_id, policy_id, body)


@router.delete("/{org_id}/capture-policies/{policy_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_capture_policy(
    policy_id: UUID,
    ctx: Annotated[_Ctx, Depends(_write_ctx)],
) -> None:
    await capture_service.delete_policy(ctx.session, ctx.org_id, policy_id)
