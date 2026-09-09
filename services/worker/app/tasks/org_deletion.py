"""Ordered Postgres cascade for org GDPR deletion jobs (MinIO/orphans are follow-ups)."""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass
from typing import Any

from sqlalchemy import text

from app.celery_app import celery_app
from app.config import get_settings
from app.db import create_engine, create_session_factory, session_as_service_account
from app.task_names import TASK_ORG_DELETE_ORGANIZATION
from app.tasks.base import IbexTask

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class _JobOutcome:
    job_id: str
    org_id: str
    status: str
    error: str | None = None

# Delete children that RESTRICT parent org removal, then soft-delete the org row.
# Keep org_deletion_jobs row (RESTRICT FK) until after soft-delete; org row remains.
_CASCADE_STATEMENTS: tuple[str, ...] = (
    "DELETE FROM ibex_core.memory_feedback WHERE org_id = CAST(:org_id AS uuid)",
    "DELETE FROM ibex_core.memory_conflict_escalations WHERE org_id = CAST(:org_id AS uuid)",
    "DELETE FROM ibex_core.memory_relationships WHERE org_id = CAST(:org_id AS uuid)",
    "DELETE FROM ibex_core.memory_labels WHERE org_id = CAST(:org_id AS uuid)",
    "UPDATE ibex_core.memories SET session_id = NULL WHERE org_id = CAST(:org_id AS uuid)",
    "DELETE FROM ibex_core.memories WHERE org_id = CAST(:org_id AS uuid)",
    "UPDATE ibex_core.sessions SET directive_version_id = NULL WHERE org_id = CAST(:org_id AS uuid)",
    "DELETE FROM ibex_core.sessions WHERE org_id = CAST(:org_id AS uuid)",
    "DELETE FROM ibex_core.directive_versions WHERE org_id = CAST(:org_id AS uuid)",
    "DELETE FROM ibex_core.directives WHERE org_id = CAST(:org_id AS uuid)",
    "DELETE FROM ibex_core.tokens WHERE org_id = CAST(:org_id AS uuid)",
    "DELETE FROM ibex_core.agents WHERE org_id = CAST(:org_id AS uuid)",
    "DELETE FROM ibex_core.organization_invites WHERE org_id = CAST(:org_id AS uuid)",
    "DELETE FROM ibex_core.users WHERE org_id = CAST(:org_id AS uuid)",
    """
    UPDATE ibex_core.organizations
    SET status = 'cancelled', deleted_at = COALESCE(deleted_at, NOW())
    WHERE id = CAST(:org_id AS uuid)
    """,
)


@celery_app.task(
    bind=True,
    base=IbexTask,
    name=TASK_ORG_DELETE_ORGANIZATION,
    queue="maintenance",
)
def delete_organization(self: IbexTask, job_id: str, org_id: str, **kwargs: Any) -> dict[str, str]:
    """Execute ordered org cascade and update org_deletion_jobs status."""
    del kwargs
    return asyncio.run(_run_delete(job_id=job_id, org_id=org_id))


async def _run_delete(*, job_id: str, org_id: str) -> dict[str, str]:
    settings = get_settings()
    if not settings.database_url:
        raise ValueError("database_url is required for org deletion")
    engine = create_engine(settings)
    factory = create_session_factory(engine)
    try:
        async with session_as_service_account(factory) as session:
            claimed = await _claim_job(session, job_id=job_id, org_id=org_id)
            if not claimed:
                return {"status": "skipped", "reason": "job_not_claimable"}
            try:
                if await _org_already_soft_deleted(session, org_id):
                    # Duplicate delivery after a prior success: keep terminal org state.
                    await _finish_job(
                        session, _JobOutcome(job_id=job_id, org_id=org_id, status="succeeded")
                    )
                    return {
                        "status": "succeeded",
                        "job_id": job_id,
                        "org_id": org_id,
                        "reason": "already_deleted",
                    }
                for stmt in _CASCADE_STATEMENTS:
                    await session.execute(text(stmt), {"org_id": org_id})
                await _finish_job(
                    session, _JobOutcome(job_id=job_id, org_id=org_id, status="succeeded")
                )
            except Exception as exc:
                logger.exception("org deletion failed job_id=%s org_id=%s", job_id, org_id)
                await session.rollback()
                async with session_as_service_account(factory) as fail_session:
                    await _finish_job(
                        fail_session,
                        _JobOutcome(
                            job_id=job_id,
                            org_id=org_id,
                            status="failed",
                            error=str(exc)[:500],
                        ),
                    )
                raise
        return {"status": "succeeded", "job_id": job_id, "org_id": org_id}
    finally:
        await engine.dispose()


async def _claim_job(session, *, job_id: str, org_id: str) -> bool:
    """Claim a pending job only.

    Failed/succeeded/running jobs are not reclaimable so delayed Celery
    redeliveries cannot resurrect a terminal job and re-run the cascade.
    API retries enqueue a new pending job row instead.
    """
    result = await session.execute(
        text(
            """
            UPDATE ibex_core.org_deletion_jobs
            SET status = 'running', started_at = NOW(), error = NULL
            WHERE id = CAST(:job_id AS uuid)
              AND org_id = CAST(:org_id AS uuid)
              AND status = 'pending'
            RETURNING id
            """
        ),
        {"job_id": job_id, "org_id": org_id},
    )
    return result.first() is not None


async def _org_already_soft_deleted(session, org_id: str) -> bool:
    result = await session.execute(
        text(
            """
            SELECT 1
            FROM ibex_core.organizations
            WHERE id = CAST(:org_id AS uuid) AND deleted_at IS NOT NULL
            """
        ),
        {"org_id": org_id},
    )
    return result.first() is not None


async def _finish_job(session, outcome: _JobOutcome) -> None:
    await session.execute(
        text(
            """
            UPDATE ibex_core.org_deletion_jobs
            SET status = :status,
                error = :error,
                finished_at = NOW()
            WHERE id = CAST(:job_id AS uuid)
              AND org_id = CAST(:org_id AS uuid)
            """
        ),
        {
            "job_id": outcome.job_id,
            "org_id": outcome.org_id,
            "status": outcome.status,
            "error": outcome.error,
        },
    )
