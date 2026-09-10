"""Token management orchestration over AuthService gRPC (no token-table SQL)."""

from __future__ import annotations

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
from authclient.tokens import TokenManager, TokenMetadataWire
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.client import ValidateResult
from app.errors import ApiError
from app.pagination import CursorPage, ListQuery, PaginationMeta
from app.permissions_codec import bitmap_to_strings, strings_to_bitmap
from app.schemas.tokens import TokenCreateRequest, TokenCreateResponse, TokenResponse
from app.services import agents as agent_service

TOKEN_NOT_FOUND_MSG = "Token not found"
_GET_BY_ID_MAX_PAGES = 100


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

    try:
        created = await access.manager.create(
            org_id=str(access.token.org_id),
            name=body.name,
            permissions=requested,
            access_token=access.access_token,
            expires_at=body.expires_at,
            user_id=access.token.user_id,
            agent_id=str(body.agent_id) if body.agent_id else None,
        )
    except InsufficientPermissionsError as exc:
        raise ApiError(
            code=INSUFFICIENT_PERMISSIONS,
            message="Insufficient permissions",
        ) from exc
    except AuthFailedError as exc:
        raise ApiError(code=INVALID_TOKEN, message="Invalid token") from exc
    except AuthUnavailableError as exc:
        raise ApiError(code=AUTH_UNAVAILABLE, message="Auth service unavailable") from exc

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
    try:
        page = await access.manager.list(
            org_id=str(access.token.org_id),
            access_token=access.access_token,
            cursor=query.cursor or "",
            limit=query.limit,
        )
    except TokenNotFoundError as exc:
        raise ApiError(code=NOT_FOUND, message=TOKEN_NOT_FOUND_MSG) from exc
    except InsufficientPermissionsError as exc:
        raise ApiError(
            code=INSUFFICIENT_PERMISSIONS,
            message="Insufficient permissions",
        ) from exc
    except AuthFailedError as exc:
        raise ApiError(code=INVALID_TOKEN, message="Invalid token") from exc
    except AuthUnavailableError as exc:
        raise ApiError(code=AUTH_UNAVAILABLE, message="Auth service unavailable") from exc

    next_cursor = page.next_cursor or None
    return CursorPage(
        data=[_meta_to_response(row) for row in page.tokens],
        pagination=PaginationMeta(
            has_more=bool(next_cursor),
            next_cursor=next_cursor,
        ),
    )


async def get_token(access: TokenAccess, token_id: UUID) -> TokenResponse:
    needle = str(token_id)
    cursor = ""
    for _ in range(_GET_BY_ID_MAX_PAGES):
        try:
            page = await access.manager.list(
                org_id=str(access.token.org_id),
                access_token=access.access_token,
                cursor=cursor,
                limit=100,
            )
        except TokenNotFoundError as exc:
            raise ApiError(code=NOT_FOUND, message=TOKEN_NOT_FOUND_MSG) from exc
        except InsufficientPermissionsError as exc:
            raise ApiError(
                code=INSUFFICIENT_PERMISSIONS,
                message="Insufficient permissions",
            ) from exc
        except AuthFailedError as exc:
            raise ApiError(code=INVALID_TOKEN, message="Invalid token") from exc
        except AuthUnavailableError as exc:
            raise ApiError(code=AUTH_UNAVAILABLE, message="Auth service unavailable") from exc

        for row in page.tokens:
            if row.token_id == needle:
                return _meta_to_response(row)
        if not page.next_cursor:
            break
        cursor = page.next_cursor
    raise ApiError(code=NOT_FOUND, message=TOKEN_NOT_FOUND_MSG)


async def revoke_token(access: TokenAccess, token_id: UUID) -> None:
    try:
        await access.manager.revoke_strict(
            org_id=str(access.token.org_id),
            token_id=str(token_id),
            access_token=access.access_token,
        )
    except TokenNotFoundError as exc:
        raise ApiError(code=NOT_FOUND, message=TOKEN_NOT_FOUND_MSG) from exc
    except AuthFailedError as exc:
        raise ApiError(code=INVALID_TOKEN, message="Invalid token") from exc
    except AuthUnavailableError as exc:
        raise ApiError(code=AUTH_UNAVAILABLE, message="Auth service unavailable") from exc


# Re-export for tests.
__all__ = [
    "TOKEN_NOT_FOUND_MSG",
    "TokenAccess",
    "create_token",
    "get_token",
    "list_tokens",
    "revoke_token",
]
