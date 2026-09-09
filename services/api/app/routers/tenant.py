"""Authenticated tenant plumbing proof (RLS GUC + WHERE org_id)."""

from __future__ import annotations

from typing import Annotated
from uuid import UUID

from apierror_py import NOT_FOUND
from fastapi import APIRouter, Depends
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.client import ValidateResult
from app.deps import org_session, require_token
from app.errors import ApiError

router = APIRouter(prefix="/v1", tags=["tenant"])


@router.get("/tenant/ping")
async def tenant_ping(
    token: Annotated[ValidateResult, Depends(require_token)],
    session: Annotated[AsyncSession, Depends(org_session)],
) -> dict[str, str]:
    """Prove org-scoped DB access: GUC set + explicit WHERE on organizations."""
    org_id = token.org_id
    row = await session.execute(
        text(  # nosemgrep: python.sqlalchemy.security.audit.avoid-sqlalchemy-text.avoid-sqlalchemy-text
            "SELECT id FROM ibex_core.organizations WHERE id = CAST(:org_id AS uuid)"
        ),
        {"org_id": str(org_id)},
    )
    found = row.scalar_one_or_none()
    if found is None:
        raise ApiError(
            code=NOT_FOUND,
            message="Organization not found for token org_id",
            detail=str(org_id),
        )
    return {"org_id": str(UUID(str(found)))}
