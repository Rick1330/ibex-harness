"""Organization persistence and lifecycle operations."""

from __future__ import annotations

import asyncio
import logging
from typing import Any
from uuid import UUID

from apierror_py import NOT_FOUND, SERVICE_DEGRADED, VALIDATION_ERROR
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.errors import ApiError
from app.revocation_publish import OrgSuspendPublisher
from app.schemas.organizations import (
    OrganizationPatch,
    OrganizationResponse,
    OrgDeletionJobResponse,
)

logger = logging.getLogger(__name__)

_ORG_NOT_FOUND = "Organization not found"
_ENQUEUE_TIMEOUT_SECONDS = 5.0


def _org_from_row(row: Any) -> OrganizationResponse:
    return OrganizationResponse(
        id=row.id,
        name=row.name,
        slug=row.slug,
        tier=row.tier,
        status=row.status,
        billing_email=row.billing_email,
        settings=row.settings or {},
        created_at=row.created_at,
        updated_at=row.updated_at,
    )


async def get_organization(session: AsyncSession, org_id: UUID) -> OrganizationResponse:
    result = await session.execute(
        text(
            """
            SELECT id, name, slug, tier, status, billing_email, settings, created_at, updated_at
            FROM ibex_core.organizations
            WHERE id = :org_id AND deleted_at IS NULL
            """
        ),
        {"org_id": str(org_id)},
    )
    row = result.mappings().first()
    if row is None:
        raise ApiError(code=NOT_FOUND, message=_ORG_NOT_FOUND)
    return _org_from_row(row)


async def patch_organization(
    session: AsyncSession, org_id: UUID, patch: OrganizationPatch
) -> OrganizationResponse:
    current = await get_organization(session, org_id)
    name = patch.name if patch.name is not None else current.name
    billing_email = (
        str(patch.billing_email) if patch.billing_email is not None else current.billing_email
    )
    settings = patch.settings if patch.settings is not None else current.settings
    result = await session.execute(
        text(
            """
            UPDATE ibex_core.organizations
            SET name = :name,
                billing_email = :billing_email,
                settings = CAST(:settings AS jsonb)
            WHERE id = :org_id AND deleted_at IS NULL
            RETURNING id, name, slug, tier, status, billing_email, settings, created_at, updated_at
            """
        ),
        {
            "org_id": str(org_id),
            "name": name,
            "billing_email": billing_email,
            "settings": _json_dumps(settings),
        },
    )
    row = result.mappings().first()
    if row is None:
        raise ApiError(code=NOT_FOUND, message=_ORG_NOT_FOUND)
    await session.commit()
    return _org_from_row(row)


async def suspend_organization(
    session: AsyncSession,
    org_id: UUID,
    publisher: OrgSuspendPublisher,
) -> OrganizationResponse:
    result = await session.execute(
        text(
            """
            UPDATE ibex_core.organizations
            SET status = 'suspended'
            WHERE id = :org_id AND deleted_at IS NULL
            RETURNING id, name, slug, tier, status, billing_email, settings, created_at, updated_at
            """
        ),
        {"org_id": str(org_id)},
    )
    row = result.mappings().first()
    if row is None:
        raise ApiError(code=NOT_FOUND, message=_ORG_NOT_FOUND)
    await session.commit()
    await publisher.publish_org_suspend(str(org_id))
    return _org_from_row(row)


async def _create_deletion_job_row(session: AsyncSession, org_id: UUID) -> Any:
    result = await session.execute(
        text(
            """
            INSERT INTO ibex_core.org_deletion_jobs (org_id, status)
            VALUES (:org_id, 'pending')
            RETURNING id, org_id, status, error, created_at, updated_at, started_at, finished_at
            """
        ),
        {"org_id": str(org_id)},
    )
    return result.mappings().first()


async def _cancel_organization(session: AsyncSession, org_id: UUID) -> None:
    await session.execute(
        text(
            """
            UPDATE ibex_core.organizations
            SET status = 'cancelled'
            WHERE id = :org_id AND deleted_at IS NULL
            """
        ),
        {"org_id": str(org_id)},
    )


async def _mark_deletion_job_failed(session: AsyncSession, job_id: UUID, exc: Exception) -> None:
    await session.execute(
        text(
            """
            UPDATE ibex_core.org_deletion_jobs
            SET status = 'failed',
                error = :error,
                finished_at = NOW()
            WHERE id = :job_id
            """
        ),
        {
            "job_id": str(job_id),
            "error": f"enqueue failed: {type(exc).__name__}"[:500],
        },
    )


async def _dispatch_deletion_enqueue(session: AsyncSession, job: Any, org_id: UUID, enqueue_fn) -> None:
    try:
        await asyncio.wait_for(
            asyncio.to_thread(enqueue_fn, str(job.id), str(org_id)),
            timeout=_ENQUEUE_TIMEOUT_SECONDS,
        )
    except Exception as exc:
        logger.warning(
            "org deletion enqueue failed job_id=%s error_class=%s",
            job.id,
            type(exc).__name__,
        )
        await _mark_deletion_job_failed(session, job.id, exc)
        await session.commit()
        raise ApiError(
            code=SERVICE_DEGRADED,
            message="Failed to enqueue organization deletion",
        ) from exc


def _deletion_job_response(job: Any) -> OrgDeletionJobResponse:
    return OrgDeletionJobResponse(
        id=job.id,
        org_id=job.org_id,
        status=job.status,
        error=job.error,
        created_at=job.created_at,
        updated_at=job.updated_at,
        started_at=job.started_at,
        finished_at=job.finished_at,
    )


async def enqueue_org_deletion(
    session: AsyncSession,
    org_id: UUID,
    *,
    enqueue_fn,
) -> OrgDeletionJobResponse:
    org = await get_organization(session, org_id)
    if org.status == "cancelled":
        raise ApiError(code=VALIDATION_ERROR, message="Organization already deleted")
    job = await _create_deletion_job_row(session, org_id)
    await _cancel_organization(session, org_id)
    await session.commit()
    if job is None:
        raise ApiError(code=VALIDATION_ERROR, message="Unable to create deletion job")
    await _dispatch_deletion_enqueue(session, job, org_id, enqueue_fn)
    return _deletion_job_response(job)


async def get_deletion_job(
    session: AsyncSession, org_id: UUID, job_id: UUID
) -> OrgDeletionJobResponse:
    result = await session.execute(
        text(
            """
            SELECT id, org_id, status, error, created_at, updated_at, started_at, finished_at
            FROM ibex_core.org_deletion_jobs
            WHERE id = :job_id AND org_id = :org_id
            """
        ),
        {"job_id": str(job_id), "org_id": str(org_id)},
    )
    row = result.mappings().first()
    if row is None:
        raise ApiError(code=NOT_FOUND, message="Deletion job not found")
    return _deletion_job_response(row)


def _json_dumps(value: dict[str, Any]) -> str:
    import json

    return json.dumps(value)
