"""Operator action ledger helpers (4.P.1 — deny without preview_token)."""

from __future__ import annotations

from uuid import UUID

from apierror_py import INSUFFICIENT_PERMISSIONS
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.errors import ApiError

_PREVIEW_REQUIRED = "preview token required"


def assert_preview_token(preview_token: str | None) -> str:
    """High-impact mutators require a non-empty preview_token (issuer lands later)."""
    token = (preview_token or "").strip()
    if not token:
        raise ApiError(code=INSUFFICIENT_PERMISSIONS, message=_PREVIEW_REQUIRED)
    return token


async def record_ledger_row(
    session: AsyncSession,
    *,
    org_id: UUID,
    actor_user_id: UUID,
    action: str,
    preview_token: str,
    idempotency_key: str,
    resource_type: str | None = None,
    resource_id: str | None = None,
    step_up_jti: str | None = None,
    requires_second_actor: bool = False,
) -> UUID:
    """Insert a ledger row. Callers must assert_preview_token first."""
    preview = assert_preview_token(preview_token)
    result = await session.execute(
        text(
            """
            INSERT INTO ibex_core.operator_action_ledger (
                org_id, actor_user_id, action, resource_type, resource_id,
                preview_token, step_up_jti, requires_second_actor, idempotency_key
            ) VALUES (
                :org_id, :actor_user_id, :action, :resource_type, :resource_id,
                :preview_token, :step_up_jti, :requires_second_actor, :idempotency_key
            )
            RETURNING id
            """
        ),
        {
            "org_id": str(org_id),
            "actor_user_id": str(actor_user_id),
            "action": action,
            "resource_type": resource_type,
            "resource_id": resource_id,
            "preview_token": preview,
            "step_up_jti": step_up_jti,
            "requires_second_actor": requires_second_actor,
            "idempotency_key": idempotency_key,
        },
    )
    row_id = result.scalar_one()
    return UUID(str(row_id))


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
