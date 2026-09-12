"""Org-scoped model-policy CRUD routes (m4.C.2)."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Query, Request, Response, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.client import ValidateResult
from app.authz import RequireOrgSettings, assert_path_org
from app.deps import org_session, require_token
from app.model_policy_publish import ModelPolicyPublisher, NoopModelPolicyPublisher
from app.pagination import CursorPage, ListQuery
from app.schemas.model_policies import (
    ModelPolicyCreate,
    ModelPolicyPatch,
    ModelPolicyResponse,
)
from app.services import model_policies as model_policy_service

router = APIRouter(prefix="/v1/organizations", tags=["model-policies"])


@dataclass(frozen=True, slots=True)
class _Ctx:
    org_id: UUID
    session: AsyncSession
    publisher: ModelPolicyPublisher


def _api_state(request: Request):
    return getattr(request.app.state, "api", None)


def _publisher(request: Request) -> ModelPolicyPublisher:
    pub = getattr(_api_state(request), "model_policy_publisher", None)
    if pub is not None:
        return pub  # type: ignore[no-any-return]
    return NoopModelPolicyPublisher()


def _make_ctx(
    request: Request, org_id: UUID, token_org_id: UUID, session: AsyncSession
) -> _Ctx:
    assert_path_org(token_org_id, org_id)
    return _Ctx(org_id=org_id, session=session, publisher=_publisher(request))


def _read_ctx(
    request: Request,
    org_id: UUID,
    token: Annotated[ValidateResult, Depends(require_token)],
    session: Annotated[AsyncSession, Depends(org_session)],
) -> _Ctx:
    return _make_ctx(request, org_id, token.org_id, session)


def _write_ctx(
    request: Request,
    org_id: UUID,
    token: RequireOrgSettings,
    session: Annotated[AsyncSession, Depends(org_session)],
) -> _Ctx:
    return _make_ctx(request, org_id, token.org_id, session)


@router.get("/{org_id}/model-policies")
async def list_model_policies(
    ctx: Annotated[_Ctx, Depends(_read_ctx)],
    query: Annotated[ListQuery, Query()],
) -> CursorPage[ModelPolicyResponse]:
    return await model_policy_service.list_policies(
        ctx.session, ctx.org_id, cursor=query.cursor, limit=query.limit
    )


@router.post("/{org_id}/model-policies", status_code=status.HTTP_201_CREATED)
async def create_model_policy(
    body: ModelPolicyCreate,
    ctx: Annotated[_Ctx, Depends(_write_ctx)],
) -> ModelPolicyResponse:
    return await model_policy_service.create_policy(
        ctx.session,
        ctx.org_id,
        body,
        deps=model_policy_service.WriteDeps(publisher=ctx.publisher),
    )


@router.get("/{org_id}/model-policies/{policy_id}")
async def get_model_policy(
    policy_id: UUID,
    ctx: Annotated[_Ctx, Depends(_read_ctx)],
) -> ModelPolicyResponse:
    return await model_policy_service.get_policy(ctx.session, ctx.org_id, policy_id)


@router.patch("/{org_id}/model-policies/{policy_id}")
async def patch_model_policy(
    policy_id: UUID,
    body: ModelPolicyPatch,
    ctx: Annotated[_Ctx, Depends(_write_ctx)],
) -> ModelPolicyResponse:
    return await model_policy_service.patch_policy(
        ctx.session,
        ctx.org_id,
        policy_id,
        body,
        deps=model_policy_service.WriteDeps(publisher=ctx.publisher),
    )


@router.delete(
    "/{org_id}/model-policies/{policy_id}", status_code=status.HTTP_204_NO_CONTENT
)
async def delete_model_policy(
    policy_id: UUID,
    ctx: Annotated[_Ctx, Depends(_write_ctx)],
) -> Response:
    await model_policy_service.delete_policy(
        ctx.session,
        ctx.org_id,
        policy_id,
        deps=model_policy_service.WriteDeps(publisher=ctx.publisher),
    )
    return Response(status_code=status.HTTP_204_NO_CONTENT)
