"""Unit tests for failed_tasks repository."""

from __future__ import annotations

from uuid import UUID

import pytest
import pytest_asyncio
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from app.config import Settings
from app.db import create_engine, create_session_factory, session_as_service_account
from app.repositories.failed_tasks import FailedTaskRecord, insert_failed_task
from app.task_names import TASK_MAINTENANCE_ALWAYS_FAIL

pytestmark = pytest.mark.usefixtures("migrated_postgres")


@pytest_asyncio.fixture
async def pg_engine(migrated_postgres: str) -> AsyncEngine:
    settings = Settings(database_url=migrated_postgres)
    engine = create_engine(settings)
    yield engine
    await engine.dispose()


@pytest.fixture
def pg_session_factory(pg_engine: AsyncEngine) -> async_sessionmaker[AsyncSession]:
    return create_session_factory(pg_engine)


@pytest_asyncio.fixture(autouse=True)
async def truncate_failed_tasks(pg_engine: AsyncEngine) -> None:
    async with pg_engine.begin() as conn:
        await conn.execute(
            text(  # nosemgrep: python.sqlalchemy.security.audit.avoid-sqlalchemy-text.avoid-sqlalchemy-text
                "TRUNCATE ibex_core.failed_tasks"
            )
        )


@pytest.mark.asyncio
async def test_insert_failed_task_persists_row(
    pg_session_factory: async_sessionmaker[AsyncSession],
) -> None:
    inserted = await insert_failed_task(
        pg_session_factory,
        FailedTaskRecord(
            task_name=TASK_MAINTENANCE_ALWAYS_FAIL,
            task_id="celery-task-abc",
            args=["x"],
            kwargs={},
            exception_type="ForcedFailureError",
            exception_message="forced failure",
            traceback_text="Traceback (most recent call last):\n  ...",
            retry_count=3,
            org_id=None,
        ),
    )
    assert inserted is True

    async with session_as_service_account(pg_session_factory) as session:
        row = (
            await session.execute(
                text(  # nosemgrep: python.sqlalchemy.security.audit.avoid-sqlalchemy-text.avoid-sqlalchemy-text
                    """
                    SELECT task_name, task_id, retry_count, org_id
                    FROM ibex_core.failed_tasks
                    WHERE task_id = :task_id
                    """
                ),
                {"task_id": "celery-task-abc"},
            )
        ).one()
    assert row.task_name == TASK_MAINTENANCE_ALWAYS_FAIL
    assert row.retry_count == 3
    assert row.org_id is None


@pytest.mark.asyncio
async def test_insert_failed_task_idempotent_on_duplicate_task_id(
    pg_session_factory: async_sessionmaker[AsyncSession],
) -> None:
    first = await insert_failed_task(
        pg_session_factory,
        FailedTaskRecord(
            task_name=TASK_MAINTENANCE_ALWAYS_FAIL,
            task_id="dup-id",
            args=[],
            kwargs={},
            exception_type="E",
            exception_message="m",
            traceback_text="t",
            retry_count=1,
            org_id=None,
        ),
    )
    second = await insert_failed_task(
        pg_session_factory,
        FailedTaskRecord(
            task_name=TASK_MAINTENANCE_ALWAYS_FAIL,
            task_id="dup-id",
            args=[],
            kwargs={},
            exception_type="E",
            exception_message="m",
            traceback_text="t",
            retry_count=1,
            org_id=None,
        ),
    )
    assert first is True
    assert second is False


@pytest.mark.asyncio
async def test_insert_failed_task_propagates_unknown_org_fk(
    pg_session_factory: async_sessionmaker[AsyncSession],
) -> None:
    unknown_org = UUID("00000000-0000-0000-0000-000000000001")
    with pytest.raises(IntegrityError):
        await insert_failed_task(
            pg_session_factory,
            FailedTaskRecord(
                task_name=TASK_MAINTENANCE_ALWAYS_FAIL,
                task_id="unknown-org-task",
                args=[],
                kwargs={},
                exception_type="E",
                exception_message="m",
                traceback_text="t",
                retry_count=1,
                org_id=unknown_org,
            ),
        )


@pytest.mark.asyncio
async def test_ibex_app_role_cannot_select_failed_tasks(pg_engine: AsyncEngine) -> None:
    async with pg_engine.connect() as conn:
        await conn.execute(text("SET ROLE ibex_app"))
        with pytest.raises(Exception, match="permission denied"):
            await conn.execute(
                text(  # nosemgrep: python.sqlalchemy.security.audit.avoid-sqlalchemy-text.avoid-sqlalchemy-text
                    "SELECT 1 FROM ibex_core.failed_tasks LIMIT 1"
                )
            )
        await conn.rollback()
