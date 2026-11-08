"""RLS org context helpers for tenant-scoped transactions.

Every memory transaction pins the non-superuser role ``ibex_app`` and sets the
organization GUC. It deliberately does **not** set ``app.is_service_account``:
that GUC means "every row visible", and setting it on a tenant read or write
turns RLS into a no-op (P0-06).
"""

from __future__ import annotations

from uuid import UUID

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession


async def set_service_org(session: AsyncSession, org_id: UUID) -> None:
    """Pin the tenant role and set the org GUC for RLS."""
    await session.execute(
        text(  # nosemgrep: python.sqlalchemy.security.audit.avoid-sqlalchemy-text.avoid-sqlalchemy-text
            "SET LOCAL ROLE ibex_app"
        )
    )
    await session.execute(
        text(  # nosemgrep: python.sqlalchemy.security.audit.avoid-sqlalchemy-text.avoid-sqlalchemy-text
            "SELECT set_config('app.current_org_id', :org_id, true)"
        ),
        {"org_id": str(org_id)},
    )
