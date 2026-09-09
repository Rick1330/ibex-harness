"""Organization management routes."""

from __future__ import annotations

from typing import Annotated
from uuid import UUID

from apierror_py import SERVICE_DEGRADED
from fastapi import APIRouter, Depends, Request, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.client import ValidateResult
from app.authz import RequireOrgSettings, RequireOwnerOrgSettings, assert_path_org
from app.deps import org_session, require_token
from app.errors import ApiError
from app.schemas.organizations import (
    OrganizationPatch,
    OrganizationResponse,
    OrgDeletionJobResponse,
)
from app.services import organizations as org_service

router = APIRouter(prefix="/v1/organizations", tags=["organizations"])


@router.get("/{org_id}")
async def get_org(
    org_id: UUID,
    token: Annotated[ValidateResult, Depends(require_token)],
    session: Annotated[AsyncSession, Depends(org_session)],
) -> OrganizationResponse:
    assert_path_org(token.org_id, org_id)
    return await org_service.get_organization(session, org_id)


@router.patch("/{org_id}")
async def patch_org(
    org_id: UUID,
    body: OrganizationPatch,
    token: RequireOrgSettings,
    session: Annotated[AsyncSession, Depends(org_session)],
) -> OrganizationResponse:
    assert_path_org(token.org_id, org_id)
    return await org_service.patch_organization(session, org_id, body)


@router.post("/{org_id}/suspend")
async def suspend_org(
    org_id: UUID,
    token: RequireOwnerOrgSettings,
    session: Annotated[AsyncSession, Depends(org_session)],
    request: Request,
) -> OrganizationResponse:
    assert_path_org(token.org_id, org_id)
    publisher = request.app.state.api.org_suspend_publisher
    if publisher is None:
        raise ApiError(
            code=SERVICE_DEGRADED,
            message="Org suspend publisher not configured",
        )
    return await org_service.suspend_organization(session, org_id, publisher)


@router.delete("/{org_id}", status_code=status.HTTP_202_ACCEPTED)
async def delete_org(
    org_id: UUID,
    token: RequireOwnerOrgSettings,
    session: Annotated[AsyncSession, Depends(org_session)],
    request: Request,
) -> OrgDeletionJobResponse:
    assert_path_org(token.org_id, org_id)
    enqueue = request.app.state.api.enqueue_org_deletion or (lambda _j, _o: None)
    return await org_service.enqueue_org_deletion(session, org_id, enqueue_fn=enqueue)


@router.get("/{org_id}/deletion-jobs/{job_id}")
async def get_org_deletion_job(
    org_id: UUID,
    job_id: UUID,
    token: RequireOwnerOrgSettings,
    session: Annotated[AsyncSession, Depends(org_session)],
) -> OrgDeletionJobResponse:
    assert_path_org(token.org_id, org_id)
    return await org_service.get_deletion_job(session, org_id, job_id)
