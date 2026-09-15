"""Operator action ledger persistence (org-scoped; no policy decisions)."""

from __future__ import annotations

from uuid import UUID

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

_INSERT_SQL = """
INSERT INTO ibex_core.operator_action_ledger (
    org_id, actor_user_id, action, resource_type, resource_id,
    preview_token, step_up_jti, requires_second_actor, idempotency_key
) VALUES (
    :org_id, :actor_user_id, :action, :resource_type, :resource_id,
    :preview_token, :step_up_jti, :requires_second_actor, :idempotency_key
)
RETURNING id
"""


async def insert_ledger_row(
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
    """Insert a ledger row filtered by org_id. Callers own preview/dual-approval policy."""
    result = await session.execute(
        text(_INSERT_SQL),
        {
            "org_id": str(org_id),
            "actor_user_id": str(actor_user_id),
            "action": action,
            "resource_type": resource_type,
            "resource_id": resource_id,
            "preview_token": preview_token,
            "step_up_jti": step_up_jti,
            "requires_second_actor": requires_second_actor,
            "idempotency_key": idempotency_key,
        },
    )
    row_id = result.scalar_one()
    return UUID(str(row_id))
