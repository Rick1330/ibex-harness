"""Unit tests for failed_tasks repository (mocked DB)."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.repositories.failed_tasks import FailedTaskRecord, _truncate_traceback, insert_failed_task


def test_truncate_traceback_short_circuit() -> None:
    assert _truncate_traceback("short") == "short"


def test_truncate_traceback_truncates_long_text() -> None:
    long_text = "x" * 70_000
    result = _truncate_traceback(long_text)
    assert len(result) < len(long_text)
    assert result.endswith("[truncated]")


def _session_with_nested() -> MagicMock:
    session = MagicMock()
    nested_cm = MagicMock()
    nested_cm.__aenter__ = AsyncMock(return_value=None)
    nested_cm.__aexit__ = AsyncMock(return_value=None)
    session.begin_nested.return_value = nested_cm
    return session


@pytest.mark.asyncio
async def test_insert_failed_task_executes_insert() -> None:
    session = _session_with_nested()
    result = MagicMock()
    result.first.return_value = ("row-id",)
    session.execute = AsyncMock(return_value=result)

    with patch("app.repositories.failed_tasks.session_as_service_account") as ctx:
        ctx.return_value.__aenter__.return_value = session
        ctx.return_value.__aexit__.return_value = None
        inserted = await insert_failed_task(
            MagicMock(),
            FailedTaskRecord(
                task_name="ibex.worker.maintenance.always_fail",
                task_id="task-1",
                args=[],
                kwargs={},
                exception_type="E",
                exception_message="m",
                traceback_text="t",
                retry_count=1,
                org_id=None,
            ),
        )

    assert inserted is True
    session.execute.assert_awaited_once()
    session.begin_nested.assert_called_once()


@pytest.mark.asyncio
async def test_insert_failed_task_duplicate_returns_false() -> None:
    session = _session_with_nested()
    result = MagicMock()
    result.first.return_value = None
    session.execute = AsyncMock(return_value=result)

    with patch("app.repositories.failed_tasks.session_as_service_account") as ctx:
        ctx.return_value.__aenter__.return_value = session
        ctx.return_value.__aexit__.return_value = None
        inserted = await insert_failed_task(
            MagicMock(),
            FailedTaskRecord(
                task_name="t",
                task_id="dup",
                args=[],
                kwargs={},
                exception_type="E",
                exception_message="m",
                traceback_text="t",
                retry_count=0,
                org_id=None,
            ),
        )

    assert inserted is False
