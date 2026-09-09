"""Organization persistence and lifecycle operations."""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Callable
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

EnqueueFn = Callable[[str, str], None]


class EnqueueNotConfiguredError(RuntimeError):
    """Raised when org deletion enqueue has no broker configured."""


def unconfigured_org_deletion_enqueue(job_id: str, org_id: str) -> None:
    """Sentinel enqueue used when celery_broker_url is unset — fail closed."""
    del job_id, org_id
    raise EnqueueNotConfiguredError("org deletion enqueue not configured")


def _row_get(row: Any, key: str) -> Any:
    """Read a column from a RowMapping or attribute-bearing row."""
    try:
        return row[key]
    except (KeyError, TypeError):
        return getattr(row, key)


def _org_from_row(row: Any) -> OrganizationResponse:
    return OrganizationResponse(
        id=_row_get(row, "id"),
        name=_row_get(row, "name"),
        slug=_row_get(row, "slug"),
        tier=_row_get(row, "tier"),
        status=_row_get(row, "status"),
        billing_email=_row_get(row, "billing_email"),
        settings=_row_get(row, "settings") or {},
        created_at=_row_get(row, "created_at"),
        updated_at=_row_get(row, "updated_at"),
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


async def _mark_deletion_job_failed(
    session: AsyncSession, job_id: UUID, org_id: UUID, exc: Exception
) -> None:
    await session.execute(
        text(
            """
            UPDATE ibex_core.org_deletion_jobs
            SET status = 'failed',
                error = :error,
                finished_at = NOW()
            WHERE id = :job_id AND org_id = :org_id
            """
        ),
        {
            "job_id": str(job_id),
            "org_id": str(org_id),
            "error": f"enqueue failed: {type(exc).__name__}"[:500],
        },
    )


async def _latest_deletion_job_status(session: AsyncSession, org_id: UUID) -> str | None:
    result = await session.execute(
        text(
            """
            SELECT status
            FROM ibex_core.org_deletion_jobs
            WHERE org_id = :org_id
            ORDER BY created_at DESC
            LIMIT 1
            """
        ),
        {"org_id": str(org_id)},
    )
    row = result.mappings().first()
    if row is None:
        return None
    return str(_row_get(row, "status"))


async def _assert_deletion_allowed(session: AsyncSession, org: OrganizationResponse) -> None:
    if org.status != "cancelled":
        return
    latest = await _latest_deletion_job_status(session, org.id)
    if latest == "failed":
        # Recovery: prior enqueue/cascade failed — allow re-DELETE to retry.
        return
    raise ApiError(code=VALIDATION_ERROR, message="Organization already deleted")


async def _dispatch_deletion_enqueue(
    session: AsyncSession, job: Any, org_id: UUID, enqueue_fn: EnqueueFn
) -> None:
    job_id = _row_get(job, "id")
    try:
        await asyncio.wait_for(
            asyncio.to_thread(enqueue_fn, str(job_id), str(org_id)),
            timeout=_ENQUEUE_TIMEOUT_SECONDS,
        )
    except Exception as exc:
        logger.warning(
            "org deletion enqueue failed job_id=%s error_class=%s",
            job_id,
            type(exc).__name__,
        )
        await _mark_deletion_job_failed(session, job_id, org_id, exc)
        await session.commit()
        raise ApiError(
            code=SERVICE_DEGRADED,
            message="Failed to enqueue organization deletion",
        ) from exc


def _deletion_job_response(job: Any) -> OrgDeletionJobResponse:
    return OrgDeletionJobResponse(
        id=_row_get(job, "id"),
        org_id=_row_get(job, "org_id"),
        status=_row_get(job, "status"),
        error=_row_get(job, "error"),
        created_at=_row_get(job, "created_at"),
        updated_at=_row_get(job, "updated_at"),
        started_at=_row_get(job, "started_at"),
        finished_at=_row_get(job, "finished_at"),
    )


async def enqueue_org_deletion(
    session: AsyncSession,
    org_id: UUID,
    *,
    enqueue_fn: EnqueueFn,
) -> OrgDeletionJobResponse:
    """Create a deletion job, enqueue first, then cancel the org (fail closed).

    If enqueue is unconfigured or fails, the org is not cancelled (or is already
    cancelled only on failed-job retry recovery after a successful re-enqueue).
    """
    if enqueue_fn is unconfigured_org_deletion_enqueue:
        raise ApiError(
            code=SERVICE_DEGRADED,
            message="Organization deletion queue not configured",
        )

    org = await get_organization(session, org_id)
    await _assert_deletion_allowed(session, org)

    # Enqueue before cancelling so a broker failure leaves the org active
    # (or, on failed-job retry, still cancelled but with a new pending job).
    job = await _create_deletion_job_row(session, org_id)
    if job is None:
        raise ApiError(code=VALIDATION_ERROR, message="Unable to create deletion job")
    await session.flush()
    await _dispatch_deletion_enqueue(session, job, org_id, enqueue_fn)
    await _cancel_organization(session, org_id)
    await session.commit()
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
