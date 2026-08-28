"""RLS org context helpers for service-account transactions."""

from __future__ import annotations

from uuid import UUID

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession


async def set_service_org(session: AsyncSession, org_id: UUID) -> None:
    """Set service-account + org GUCs for ibex_app RLS (defense in depth)."""
    await session.execute(
        text(  # nosemgrep: python.sqlalchemy.security.audit.avoid-sqlalchemy-text.avoid-sqlalchemy-text
            "SELECT set_config('app.is_service_account', 'true', true)"
        )
    )
    await session.execute(
        text(  # nosemgrep: python.sqlalchemy.security.audit.avoid-sqlalchemy-text.avoid-sqlalchemy-text
            "SELECT set_config('app.current_org_id', :org_id, true)"
        ),
        {"org_id": str(org_id)},
    )
