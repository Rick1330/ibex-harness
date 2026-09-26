"""Legal hold set/clear routes (4.P.3)."""

from __future__ import annotations

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.client import ValidateResult
from app.authz import RequireLegalHoldManage, assert_path_org
from app.deps import operator_org_session, org_session, require_token
from app.schemas.legal_holds import LegalHoldCreate, LegalHoldResponse
from app.services import legal_holds as hold_service

router = APIRouter(prefix="/v1/organizations", tags=["legal-holds"])


def _session_subject(token: object) -> str:
    subject = getattr(token, "subject", None) or getattr(token, "user_id", None)
    if not subject:
        from apierror_py import INSUFFICIENT_PERMISSIONS

        from app.errors import ApiError

        raise ApiError(code=INSUFFICIENT_PERMISSIONS, message="Session subject required")
    return str(subject)


@router.get("/{org_id}/legal-holds")
async def list_holds(
    org_id: UUID,
    token: Annotated[ValidateResult, Depends(require_token)],
    session: Annotated[AsyncSession, Depends(org_session)],
) -> list[LegalHoldResponse]:
    assert_path_org(token.org_id, org_id)
    return await hold_service.list_active_holds(session, org_id)


@router.post("/{org_id}/legal-holds", status_code=status.HTTP_201_CREATED)
async def set_hold(
    org_id: UUID,
    body: LegalHoldCreate,
    token: RequireLegalHoldManage,
    session: Annotated[AsyncSession, Depends(operator_org_session)],
) -> LegalHoldResponse:
    assert_path_org(token.org_id, org_id)
    return await hold_service.set_hold(session, org_id, body, set_by=_session_subject(token))


@router.post("/{org_id}/legal-holds/{hold_id}/clear")
async def clear_hold(
    org_id: UUID,
    hold_id: UUID,
    token: RequireLegalHoldManage,
    session: Annotated[AsyncSession, Depends(operator_org_session)],
) -> LegalHoldResponse:
    assert_path_org(token.org_id, org_id)
    return await hold_service.clear_hold(
        session, org_id, hold_id, cleared_by=_session_subject(token)
    )
