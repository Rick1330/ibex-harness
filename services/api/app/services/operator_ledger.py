"""Operator action ledger helpers (4.P.1 — deny without preview_token)."""

from __future__ import annotations

from collections.abc import Awaitable
from typing import Protocol
from uuid import UUID

from apierror_py import INSUFFICIENT_PERMISSIONS
from sqlalchemy.ext.asyncio import AsyncSession

from app.errors import ApiError
from app.repositories import operator_ledger as ledger_repo
from app.repositories.operator_ledger import LedgerRowInsert

_PREVIEW_REQUIRED = "preview token required"


class LedgerInsert(Protocol):
    def __call__(self, session: AsyncSession, row: LedgerRowInsert) -> Awaitable[UUID]: ...


def assert_preview_token(preview_token: str | None) -> str:
    """High-impact mutators require a non-empty preview_token (issuer lands later)."""
    token = (preview_token or "").strip()
    if not token:
        raise ApiError(code=INSUFFICIENT_PERMISSIONS, message=_PREVIEW_REQUIRED)
    return token


async def record_ledger_row(
    session: AsyncSession,
    row: LedgerRowInsert,
    *,
    insert: LedgerInsert | None = None,
) -> UUID:
    """Insert a ledger row. Callers must assert_preview_token first (also enforced here)."""
    preview = assert_preview_token(row.preview_token)
    write: LedgerInsert = insert or ledger_repo.insert_ledger_row
    return await write(
        session,
        LedgerRowInsert(
            org_id=row.org_id,
            actor_user_id=row.actor_user_id,
            action=row.action,
            preview_token=preview,
            idempotency_key=row.idempotency_key,
            resource_type=row.resource_type,
            resource_id=row.resource_id,
            step_up_jti=row.step_up_jti,
            requires_second_actor=row.requires_second_actor,
        ),
    )


def assert_dual_approval_satisfied(
    *,
    requires_second_actor: bool,
    second_actor_user_id: UUID | None,
    actor_user_id: UUID,
) -> None:
    """Hook-only dual-approval gate: deny until a different second actor is recorded."""
    if not requires_second_actor:
        return
    if second_actor_user_id is None or second_actor_user_id == actor_user_id:
        raise ApiError(
            code=INSUFFICIENT_PERMISSIONS,
            message="second actor approval required",
        )
