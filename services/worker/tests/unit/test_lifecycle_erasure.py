"""Unit tests for the erasure consumer's entry point.

``app.tasks.lifecycle_erasure`` is a facade over seven modules, so the only
thing this file covers is what the package itself declares: the Celery task's
registered name, the time limits derived from the configured job budget (a fixed
limit killed a legal longer budget), the budgets those limits come from, and the
pre-flight result when the deployment has no database — ``skipped``, before any
engine is created or row claimed.

The rules the receipt depends on are split one module per subject:

* ``test_lifecycle_erasure_decisions.py`` — the pure decision rules;
* ``test_lifecycle_erasure_store_targets.py`` — which stores run, and with what;
* ``test_lifecycle_erasure_staging.py`` — the PostgreSQL and object-store stages;
* ``test_lifecycle_erasure_cache.py`` — the Redis stages and their key guards;
* ``test_lifecycle_erasure_sql.py`` — the shape of the statements;
* ``test_lifecycle_erasure_contract.py`` — declarations that mirror something
  outside this package;
* ``test_lifecycle_erasure_clickhouse.py`` — the reused ClickHouse op;
* ``test_lifecycle_erasure_sweep.py`` — claim, retire, read and settle.

The stores themselves are exercised against real PostgreSQL and ClickHouse in
``tests/integration/test_memory_lifecycle_erasure_postgres.py``.
"""

from __future__ import annotations

import pytest

import app.tasks  # noqa: F401 — registers the task with the Celery app
from app.config import Settings
from app.tasks import lifecycle_erasure as le


def test_task_registration_and_time_limits() -> None:
    from app.celery_app import route_for_task
    from app.task_names import TASK_LIFECYCLE_ERASE_MEMORY

    assert le.erase_memory.name == TASK_LIFECYCLE_ERASE_MEMORY
    # The decorator applied the derivation from the settings loaded at import.
    assert le.erase_memory.soft_time_limit == le._ERASURE_SOFT_LIMIT
    assert le.erase_memory.time_limit == le._ERASURE_TIME_LIMIT
    assert le._ERASURE_SOFT_LIMIT == le._task_limits(900.0)[0]
    from app.celery_app import create_celery_app

    celery = create_celery_app(
        Settings(
            broker_url="redis://localhost:6379/1",
            result_backend="redis://localhost:6379/3",
            env="development",
        )
    )
    assert route_for_task(celery, TASK_LIFECYCLE_ERASE_MEMORY) == "maintenance"
    assert "lifecycle-erase-memory" in (celery.conf.beat_schedule or {})


def test_task_limits_cover_a_non_default_job_budget() -> None:
    """A legal 1800 s budget must not be killed by a fixed 900 s task limit."""
    original = (le.erase_memory.soft_time_limit, le.erase_memory.time_limit)
    try:
        le.configure_erasure_task_limits(1800.0)
        assert le.erase_memory.soft_time_limit >= 1800.0
        assert le.erase_memory.soft_time_limit == int(
            1800.0 + le._ERASURE_SETTLEMENT_HEADROOM_SECONDS
        )
        assert le.erase_memory.time_limit > le.erase_memory.soft_time_limit
    finally:
        le.erase_memory.soft_time_limit, le.erase_memory.time_limit = original


def test_deadline_defaults_match_the_contract() -> None:
    settings = Settings()
    assert settings.lifecycle_erasure_store_timeout_seconds == 120.0
    assert settings.lifecycle_erasure_job_timeout_seconds == 900.0


@pytest.mark.asyncio
async def test_sweep_skips_without_a_database_url(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("POSTGRES_DSN", raising=False)
    monkeypatch.delenv("IBEX_WORKER_DATABASE_URL", raising=False)
    out = await le._run_sweep(settings=Settings(database_url=None))
    assert out == {"status": "skipped", "reason": "missing_dsn"}
