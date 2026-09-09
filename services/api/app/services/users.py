"""User persistence, invites, last-owner protection, soft-delete + PAT revoke."""

from __future__ import annotations

import asyncio
import hashlib
import secrets
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any, Protocol
from uuid import UUID

from apierror_py import INSUFFICIENT_PERMISSIONS, LAST_OWNER_PROTECTED, NOT_FOUND, VALIDATION_ERROR
from authclient.errors import AuthUnavailableError
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.errors import ApiError
from app.pagination import CursorPage, decode_cursor, encode_cursor, page_from_rows
from app.schemas.users import UserCreate, UserPatch, UserResponse

_USER_NOT_FOUND = "User not found"
_REVOKE_MAX_ATTEMPTS = 3
_REVOKE_BACKOFF_BASE_SECONDS = 0.05
_REVOKE_BACKOFF_MAX_SECONDS = 1.0


class TokenRevoker(Protocol):
    async def revoke(
        self,
        *,
        org_id: str,
        token_id: str,
        access_token: str,
        reason: str | None = None,
    ) -> None: ...


@dataclass(frozen=True)
class RevokeContext:
    revoker: TokenRevoker
    access_token: str


@dataclass(frozen=True)
class PatchUserArgs:
    """Packed args for patch_user (keeps the public surface under CodeScene limits)."""

    org_id: UUID
    user_id: UUID
    patch: UserPatch
    caller_role: str


def _user_from_row(row: Any, *, invite_token: str | None = None) -> UserResponse:
    return UserResponse(
        id=row.id,
        org_id=row.org_id,
        email=row.email,
        name=row.name,
        role=row.role,
        status=row.status,
        created_at=row.created_at,
        updated_at=row.updated_at,
        invite_token=invite_token,
    )


@dataclass(frozen=True)
class _UserListCursor:
    created_at: str | None
    user_id: str | None


def _parse_user_list_cursor(cursor: str | None) -> _UserListCursor:
    try:
        payload = decode_cursor(cursor)
    except (TypeError, ValueError) as exc:
        raise ApiError(code=VALIDATION_ERROR, message="Invalid cursor") from exc
    if payload is None:
        return _UserListCursor(None, None)
    created_at = payload.get("created_at")
    user_id = payload.get("id")
    if not created_at or not user_id:
        raise ApiError(code=VALIDATION_ERROR, message="Invalid cursor")
    return _UserListCursor(str(created_at), str(user_id))


async def _fetch_users_first_page(session: AsyncSession, org_id: UUID, limit: int) -> list[Any]:
    result = await session.execute(
        text(
            """
            SELECT id, org_id, email, name, role, status, created_at, updated_at
            FROM ibex_core.users
            WHERE org_id = :org_id AND deleted_at IS NULL
            ORDER BY created_at DESC, id DESC
            LIMIT :limit
            """
        ),
        {"org_id": str(org_id), "limit": limit + 1},
    )
    return list(result.mappings().all())


async def _fetch_users_after_cursor(
    session: AsyncSession,
    org_id: UUID,
    cursor: _UserListCursor,
    limit: int,
) -> list[Any]:
    result = await session.execute(
        text(
            """
            SELECT id, org_id, email, name, role, status, created_at, updated_at
            FROM ibex_core.users
            WHERE org_id = :org_id AND deleted_at IS NULL
              AND (created_at < CAST(:created_at AS timestamptz)
                   OR (created_at = CAST(:created_at AS timestamptz) AND id < CAST(:id AS uuid)))
            ORDER BY created_at DESC, id DESC
            LIMIT :limit
            """
        ),
        {
            "org_id": str(org_id),
            "created_at": cursor.created_at,
            "id": cursor.user_id,
            "limit": limit + 1,
        },
    )
    return list(result.mappings().all())


def _next_user_list_payload(users: list[UserResponse], limit: int) -> dict[str, str] | None:
    if len(users) <= limit:
        return None
    last = users[limit - 1]
    return {"created_at": last.created_at.isoformat(), "id": str(last.id)}


async def list_users(
    session: AsyncSession,
    org_id: UUID,
    *,
    cursor: str | None,
    limit: int,
) -> CursorPage[UserResponse]:
    list_cursor = _parse_user_list_cursor(cursor)
    if list_cursor.created_at is None:
        rows = await _fetch_users_first_page(session, org_id, limit)
    else:
        rows = await _fetch_users_after_cursor(session, org_id, list_cursor, limit)
    users = [_user_from_row(r) for r in rows]
    payload = _next_user_list_payload(users, limit)
    next_cursor = encode_cursor(payload) if payload is not None else None
    return page_from_rows(users, limit=limit, next_cursor=next_cursor)


async def get_user(session: AsyncSession, org_id: UUID, user_id: UUID) -> UserResponse:
    result = await session.execute(
        text(
            """
            SELECT id, org_id, email, name, role, status, created_at, updated_at
            FROM ibex_core.users
            WHERE id = :user_id AND org_id = :org_id AND deleted_at IS NULL
            """
        ),
        {"user_id": str(user_id), "org_id": str(org_id)},
    )
    row = result.mappings().first()
    if row is None:
        raise ApiError(code=NOT_FOUND, message=_USER_NOT_FOUND)
    return _user_from_row(row)


async def _insert_invited_user(session: AsyncSession, org_id: UUID, body: UserCreate) -> Any:
    result = await session.execute(
        text(
            """
            INSERT INTO ibex_core.users (org_id, email, name, role, status)
            VALUES (:org_id, :email, :name, :role, 'invited')
            RETURNING id, org_id, email, name, role, status, created_at, updated_at
            """
        ),
        {
            "org_id": str(org_id),
            "email": str(body.email).lower(),
            "name": body.name,
            "role": body.role,
        },
    )
    row = result.mappings().first()
    if row is None:
        raise ApiError(code=VALIDATION_ERROR, message="Unable to create user")
    return row


@dataclass(frozen=True)
class _InviteRow:
    org_id: UUID
    email: str
    role: str
    token_hash: str
    expires_at: datetime
    created_by: UUID | None


async def _insert_invite_row(session: AsyncSession, invite: _InviteRow) -> None:
    await session.execute(
        text(
            """
            INSERT INTO ibex_core.organization_invites
                (org_id, email, role, token_hash, expires_at, created_by)
            VALUES (:org_id, :email, :role, :token_hash, :expires_at, :created_by)
            """
        ),
        {
            "org_id": str(invite.org_id),
            "email": invite.email,
            "role": invite.role,
            "token_hash": invite.token_hash,
            "expires_at": invite.expires_at,
            "created_by": str(invite.created_by) if invite.created_by else None,
        },
    )


async def create_user_invite(
    session: AsyncSession,
    org_id: UUID,
    body: UserCreate,
    *,
    created_by: UUID | None,
) -> UserResponse:
    raw_token = secrets.token_urlsafe(32)
    token_hash = hashlib.sha256(raw_token.encode("utf-8")).hexdigest()
    expires_at = datetime.now(UTC) + timedelta(hours=72)
    try:
        row = await _insert_invited_user(session, org_id, body)
        await _insert_invite_row(
            session,
            _InviteRow(
                org_id=org_id,
                email=str(body.email).lower(),
                role=body.role,
                token_hash=token_hash,
                expires_at=expires_at,
                created_by=created_by,
            ),
        )
        await session.commit()
    except IntegrityError as exc:
        await session.rollback()
        raise ApiError(
            code=VALIDATION_ERROR,
            message="User with this email already exists in the organization",
        ) from exc
    return _user_from_row(row, invite_token=raw_token)


def _is_owner_demotion(current_role: str, new_role: str | None) -> bool:
    return new_role is not None and current_role == "owner" and new_role != "owner"


async def patch_user(session: AsyncSession, args: PatchUserArgs) -> UserResponse:
    current = await get_user(session, args.org_id, args.user_id)
    name = args.patch.name if args.patch.name is not None else current.name
    role = args.patch.role if args.patch.role is not None else current.role

    if args.patch.role == "owner" and args.caller_role != "owner":
        raise ApiError(
            code=INSUFFICIENT_PERMISSIONS,
            message="Only an owner can promote a user to owner",
        )

    if _is_owner_demotion(current.role, args.patch.role):
        await _assert_not_last_owner(session, args.org_id)

    result = await session.execute(
        text(
            """
            UPDATE ibex_core.users
            SET name = :name, role = :role
            WHERE id = :user_id AND org_id = :org_id AND deleted_at IS NULL
            RETURNING id, org_id, email, name, role, status, created_at, updated_at
            """
        ),
        {
            "user_id": str(args.user_id),
            "org_id": str(args.org_id),
            "name": name,
            "role": role,
        },
    )
    row = result.mappings().first()
    if row is None:
        raise ApiError(code=NOT_FOUND, message=_USER_NOT_FOUND)
    await session.commit()
    return _user_from_row(row)


def _revoke_backoff_seconds(attempt: int) -> float:
    """Full-jitter exponential backoff for AuthUnavailableError retries."""
    cap = min(_REVOKE_BACKOFF_BASE_SECONDS * (2**attempt), _REVOKE_BACKOFF_MAX_SECONDS)
    return (secrets.randbelow(1_000_000) / 1_000_000) * cap


async def _revoke_tokens_before_delete(
    revoke: RevokeContext,
    *,
    org_id: UUID,
    token_ids: list[str],
) -> None:
    last_unavailable: AuthUnavailableError | None = None
    for attempt in range(_REVOKE_MAX_ATTEMPTS):
        try:
            for token_id in token_ids:
                await revoke.revoker.revoke(
                    org_id=str(org_id),
                    token_id=token_id,
                    access_token=revoke.access_token,
                    reason="user_deleted",
                )
            return
        except AuthUnavailableError as exc:
            last_unavailable = exc
            if attempt >= _REVOKE_MAX_ATTEMPTS - 1:
                raise
            await asyncio.sleep(_revoke_backoff_seconds(attempt))
    if last_unavailable is not None:
        raise last_unavailable


async def soft_delete_user(
    session: AsyncSession,
    org_id: UUID,
    user_id: UUID,
    revoke: RevokeContext,
) -> None:
    current = await get_user(session, org_id, user_id)
    if current.role == "owner":
        await _assert_not_last_owner(session, org_id)

    token_ids = await _list_active_token_ids(session, org_id, user_id)
    try:
        await _revoke_tokens_before_delete(revoke, org_id=org_id, token_ids=token_ids)
    except Exception:
        await session.rollback()
        raise

    result = await session.execute(
        text(
            """
            UPDATE ibex_core.users
            SET status = 'deactivated', deleted_at = NOW()
            WHERE id = :user_id AND org_id = :org_id AND deleted_at IS NULL
            """
        ),
        {"user_id": str(user_id), "org_id": str(org_id)},
    )
    if result.rowcount == 0:
        raise ApiError(code=NOT_FOUND, message=_USER_NOT_FOUND)
    await session.commit()


async def _list_active_token_ids(
    session: AsyncSession, org_id: UUID, user_id: UUID
) -> list[str]:
    result = await session.execute(
        text(
            """
            SELECT id::text AS id
            FROM ibex_core.tokens
            WHERE org_id = :org_id AND user_id = :user_id AND is_revoked = false
            ORDER BY created_at ASC, id ASC
            """
        ),
        {"org_id": str(org_id), "user_id": str(user_id)},
    )
    return [str(r.id) for r in result.mappings().all()]


async def _assert_not_last_owner(session: AsyncSession, org_id: UUID) -> None:
    # Lock owner rows (not COUNT) — Postgres rejects FOR UPDATE with aggregates.
    result = await session.execute(
        text(
            """
            SELECT id
            FROM ibex_core.users
            WHERE org_id = :org_id
              AND role = 'owner'
              AND deleted_at IS NULL
            FOR UPDATE
            """
        ),
        {"org_id": str(org_id)},
    )
    if len(result.fetchall()) <= 1:
        raise ApiError(
            code=LAST_OWNER_PROTECTED,
            message="Cannot demote or remove the last remaining owner",
        )
