"""Token management orchestration over AuthService gRPC (no token-table SQL)."""

from __future__ import annotations

import time
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from uuid import UUID

from apierror_py import (
    AUTH_UNAVAILABLE,
    INSUFFICIENT_PERMISSIONS,
    INVALID_TOKEN,
    NOT_FOUND,
    PERMISSION_ELEVATION_DENIED,
)
from authclient.errors import (
    AuthFailedError,
    AuthUnavailableError,
    InsufficientPermissionsError,
    TokenNotFoundError,
)
from authclient.permissions import has_permission
from authclient.tokens import CreateTokenParams, ListTokensWire, TokenManager, TokenMetadataWire
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.client import ValidateResult
from app.errors import ApiError
from app.pagination import CursorPage, ListQuery, PaginationMeta
from app.permissions_codec import bitmap_to_strings, strings_to_bitmap
from app.schemas.tokens import TokenCreateRequest, TokenCreateResponse, TokenResponse
from app.services import agents as agent_service

TOKEN_NOT_FOUND_MSG = "Token not found"  # nosec B105 — user-facing error text, not a credential
_GET_BY_ID_DEADLINE_S = 5.0
_GET_BY_ID_PAGE_SIZE = 100


@dataclass(frozen=True, slots=True)
class TokenAccess:
    """Caller context for Auth management RPCs (bearer passed through)."""

    token: ValidateResult
    access_token: str
    manager: TokenManager


def _meta_to_response(row: TokenMetadataWire) -> TokenResponse:
    return TokenResponse(
        id=UUID(row.token_id),
        name=row.name,
        permissions=bitmap_to_strings(row.permissions),
        prefix=row.prefix,
        expires_at=row.expires_at,
        created_at=row.created_at,
        revoked_at=row.revoked_at,
        is_revoked=row.is_revoked,
    )


def _map_token_rpc(exc: BaseException) -> ApiError:
    if isinstance(exc, TokenNotFoundError):
        return ApiError(code=NOT_FOUND, message=TOKEN_NOT_FOUND_MSG)
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
        TokenNotFoundError,
        InsufficientPermissionsError,
        AuthFailedError,
        AuthUnavailableError,
    ) as exc:
        raise _map_token_rpc(exc) from exc


async def create_token(
    session: AsyncSession,
    access: TokenAccess,
    body: TokenCreateRequest,
) -> TokenCreateResponse:
    requested = strings_to_bitmap(body.permissions)
    if not has_permission(access.token.permissions, requested):
        raise ApiError(
            code=PERMISSION_ELEVATION_DENIED,
            message="Cannot grant permissions the caller does not hold",
        )
    if body.agent_id is not None:
        await agent_service.get_agent(session, access.token.org_id, body.agent_id)

    created = await _call_auth(
        lambda: access.manager.create(
            CreateTokenParams(
                org_id=str(access.token.org_id),
                name=body.name,
                permissions=requested,
                access_token=access.access_token,
                expires_at=body.expires_at,
                user_id=access.token.user_id,
                agent_id=str(body.agent_id) if body.agent_id else None,
            )
        )
    )

    return TokenCreateResponse(
        id=UUID(created.token_id),
        name=body.name,
        token=created.plaintext,
        permissions=bitmap_to_strings(requested),
        prefix=created.prefix,
        expires_at=body.expires_at,
        created_at=created.created_at,
    )


async def list_tokens(access: TokenAccess, query: ListQuery) -> CursorPage[TokenResponse]:
    page = await _list_page(
        access,
        cursor=query.cursor or "",
        limit=query.limit,
    )
    next_cursor = page.next_cursor or None
    return CursorPage(
        data=[_meta_to_response(row) for row in page.tokens],
        pagination=PaginationMeta(
            has_more=bool(next_cursor),
            next_cursor=next_cursor,
        ),
    )


async def _list_page(access: TokenAccess, *, cursor: str, limit: int) -> ListTokensWire:
    return await _call_auth(
        lambda: access.manager.list(
            org_id=str(access.token.org_id),
            access_token=access.access_token,
            cursor=cursor,
            limit=limit,
        )
    )


async def get_token(access: TokenAccess, token_id: UUID) -> TokenResponse:
    row = await _scan_token_meta(access, str(token_id))
    if row is None:
        raise ApiError(code=NOT_FOUND, message=TOKEN_NOT_FOUND_MSG)
    return _meta_to_response(row)


async def _scan_token_meta(access: TokenAccess, needle: str) -> TokenMetadataWire | None:
    """Return matching metadata, or None only after a fully exhausted list.

    Deadline expiry or a repeated cursor means the scan did not finish; those
    map to AUTH_UNAVAILABLE rather than a definitive NOT_FOUND.
    """
    cursor = ""
    seen: set[str] = set()
    deadline = time.monotonic() + _GET_BY_ID_DEADLINE_S
    while time.monotonic() < deadline and cursor not in seen:
        seen.add(cursor)
        page = await _list_page(access, cursor=cursor, limit=_GET_BY_ID_PAGE_SIZE)
        for row in page.tokens:
            if row.token_id == needle:
                return row
        if not page.next_cursor:
            return None
        cursor = page.next_cursor
    raise ApiError(code=AUTH_UNAVAILABLE, message="Auth service unavailable")


async def revoke_token(access: TokenAccess, token_id: UUID) -> None:
    await _call_auth(
        lambda: access.manager.revoke_strict(
            org_id=str(access.token.org_id),
            token_id=str(token_id),
            access_token=access.access_token,
        )
    )


__all__ = [
    "TOKEN_NOT_FOUND_MSG",
    "TokenAccess",
    "create_token",
    "get_token",
    "list_tokens",
    "revoke_token",
]
