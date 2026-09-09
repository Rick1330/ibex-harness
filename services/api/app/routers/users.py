"""User management routes."""

from __future__ import annotations

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Header, Query, Request, Response, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.client import ValidateResult, parse_authorization_header
from app.authz import RequireUserManage
from app.deps import org_id_from_token, org_session, require_token
from app.pagination import CursorPage, ListQuery
from app.schemas.users import UserCreate, UserPatch, UserResponse
from app.services import users as user_service
from app.services.users import RevokeContext

router = APIRouter(prefix="/v1/users", tags=["users"])


def _list_query(
    cursor: Annotated[str | None, Query()] = None,
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
) -> ListQuery:
    return ListQuery(cursor=cursor, limit=limit)


def _bearer_token(
    authorization: Annotated[str | None, Header(alias="Authorization")] = None,
) -> str:
    return parse_authorization_header(authorization)


def _revoke_context(
    request: Request,
    access_token: Annotated[str, Depends(_bearer_token)],
) -> RevokeContext:
    return RevokeContext(
        revoker=request.app.state.api.token_revoker,
        access_token=access_token,
    )


@router.get("", response_model=CursorPage[UserResponse])
async def list_users(
    token: Annotated[ValidateResult, Depends(require_token)],
    session: Annotated[AsyncSession, Depends(org_session)],
    org_id: Annotated[UUID, Depends(org_id_from_token)],
    query: Annotated[ListQuery, Depends(_list_query)],
) -> CursorPage[UserResponse]:
    del token
    return await user_service.list_users(
        session, org_id, cursor=query.cursor, limit=query.limit
    )


@router.post("", status_code=status.HTTP_201_CREATED, response_model=UserResponse)
async def create_user(
    body: UserCreate,
    token: RequireUserManage,
    session: Annotated[AsyncSession, Depends(org_session)],
) -> UserResponse:
    created_by = UUID(token.user_id) if token.user_id else None
    return await user_service.create_user_invite(
        session, token.org_id, body, created_by=created_by
    )


@router.get("/{user_id}", response_model=UserResponse)
async def get_user(
    user_id: UUID,
    token: Annotated[ValidateResult, Depends(require_token)],
    session: Annotated[AsyncSession, Depends(org_session)],
) -> UserResponse:
    return await user_service.get_user(session, token.org_id, user_id)


@router.patch("/{user_id}", response_model=UserResponse)
async def patch_user(
    user_id: UUID,
    body: UserPatch,
    token: RequireUserManage,
    session: Annotated[AsyncSession, Depends(org_session)],
) -> UserResponse:
    return await user_service.patch_user(session, token.org_id, user_id, body)


@router.delete("/{user_id}", status_code=status.HTTP_204_NO_CONTENT, response_class=Response)
async def delete_user(
    user_id: UUID,
    token: RequireUserManage,
    session: Annotated[AsyncSession, Depends(org_session)],
    revoke: Annotated[RevokeContext, Depends(_revoke_context)],
) -> Response:
    await user_service.soft_delete_user(session, token.org_id, user_id, revoke)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
