"""RLS org context helpers for tenant-scoped transactions.

Every memory transaction pins the non-superuser role ``ibex_app`` and sets the
organization GUC. It deliberately does **not** set ``app.is_service_account``:
that GUC means "every row visible", and setting it on a tenant read or write
turns RLS into a no-op (P0-06). Because the GUC is transaction-local, a pooled
session that previously ran a service-account transaction cannot leak the bypass
into the next one — but the helper clears it explicitly anyway, so a caller that
set it before opening the tenant scope cannot retain it.
"""

from __future__ import annotations

from uuid import UUID

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

_CLEAR_BYPASS_SQL = "SELECT set_config('app.is_service_account', 'false', true)"
_PIN_TENANT_ROLE_SQL = "SET LOCAL ROLE ibex_app"
_SET_ORG_SQL = "SELECT set_config('app.current_org_id', :org_id, true)"


async def set_service_org(session: AsyncSession, org_id: UUID) -> None:
    """Pin the tenant role and org GUC for RLS, clearing any inherited bypass."""
    await session.execute(
        text(  # nosemgrep: python.sqlalchemy.security.audit.avoid-sqlalchemy-text.avoid-sqlalchemy-text
            _CLEAR_BYPASS_SQL
        )
    )
    await session.execute(
        text(  # nosemgrep: python.sqlalchemy.security.audit.avoid-sqlalchemy-text.avoid-sqlalchemy-text
            _PIN_TENANT_ROLE_SQL
        )
    )
    await session.execute(
        text(  # nosemgrep: python.sqlalchemy.security.audit.avoid-sqlalchemy-text.avoid-sqlalchemy-text
            _SET_ORG_SQL
        ),
        {"org_id": str(org_id)},
    )
