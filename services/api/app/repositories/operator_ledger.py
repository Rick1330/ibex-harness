"""Operator action ledger persistence (org-scoped; no policy decisions)."""

from __future__ import annotations

from dataclasses import dataclass
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


@dataclass(frozen=True, slots=True)
class LedgerRowInsert:
    org_id: UUID
    actor_user_id: UUID
    action: str
    preview_token: str
    idempotency_key: str
    resource_type: str | None = None
    resource_id: str | None = None
    step_up_jti: str | None = None
    requires_second_actor: bool = False


async def insert_ledger_row(session: AsyncSession, row: LedgerRowInsert) -> UUID:
    """Insert a ledger row filtered by org_id. Callers own preview/dual-approval policy."""
    result = await session.execute(
        text(_INSERT_SQL),
        {
            "org_id": str(row.org_id),
            "actor_user_id": str(row.actor_user_id),
            "action": row.action,
            "resource_type": row.resource_type,
            "resource_id": row.resource_id,
            "preview_token": row.preview_token,
            "step_up_jti": row.step_up_jti,
            "requires_second_actor": row.requires_second_actor,
            "idempotency_key": row.idempotency_key,
        },
    )
    row_id = result.scalar_one()
    return UUID(str(row_id))
