"""Token management routes (Create/List/Get/Delete via AuthService gRPC)."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Header, Query, Request, Response, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.client import ValidateResult, parse_authorization_header
from app.deps import org_session, require_token
from app.pagination import CursorPage, ListQuery
from app.schemas.tokens import TokenCreateRequest, TokenCreateResponse, TokenResponse
from app.services import tokens as token_service
from app.services.tokens import TokenAccess

router = APIRouter(prefix="/v1/tokens", tags=["tokens"])


def _list_query(
    cursor: Annotated[str | None, Query()] = None,
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
) -> ListQuery:
    return ListQuery(cursor=cursor, limit=limit)


def _bearer_token(
    authorization: Annotated[str | None, Header(alias="Authorization")] = None,
) -> str:
    return parse_authorization_header(authorization)


@dataclass(frozen=True)
class _TokenCtx:
    access: TokenAccess
    session: AsyncSession


def _token_ctx(
    request: Request,
    token: Annotated[ValidateResult, Depends(require_token)],
    access_token: Annotated[str, Depends(_bearer_token)],
    session: Annotated[AsyncSession, Depends(org_session)],
) -> _TokenCtx:
    manager = request.app.state.api.token_manager
    return _TokenCtx(
        access=TokenAccess(token=token, access_token=access_token, manager=manager),
        session=session,
    )


@router.get("")
async def list_tokens(
    ctx: Annotated[_TokenCtx, Depends(_token_ctx)],
    query: Annotated[ListQuery, Depends(_list_query)],
) -> CursorPage[TokenResponse]:
    return await token_service.list_tokens(ctx.access, query)


@router.post("", status_code=status.HTTP_201_CREATED)
async def create_token(
    body: TokenCreateRequest,
    ctx: Annotated[_TokenCtx, Depends(_token_ctx)],
) -> TokenCreateResponse:
    return await token_service.create_token(ctx.session, ctx.access, body)


@router.get("/{token_id}")
async def get_token(
    token_id: UUID,
    ctx: Annotated[_TokenCtx, Depends(_token_ctx)],
) -> TokenResponse:
    return await token_service.get_token(ctx.access, token_id)


@router.delete("/{token_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_token(
    token_id: UUID,
    ctx: Annotated[_TokenCtx, Depends(_token_ctx)],
) -> Response:
    await token_service.revoke_token(ctx.access, token_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
