"""Shared pytest fixtures for worker tests."""

from __future__ import annotations

import os

import pytest
import pytest_asyncio
from sqlalchemy import text

from app.config import Settings
from app.db import create_engine


def _postgres_dsn_from_env() -> str | None:
    return (
        os.getenv("POSTGRES_DSN")
        or os.getenv("POSTGRES_TEST_DSN")
        or os.getenv("IBEX_WORKER_DATABASE_URL")
    )


@pytest.fixture(scope="session")
def postgres_dsn() -> str:
    dsn = _postgres_dsn_from_env()
    if not dsn:
        pytest.skip("POSTGRES_DSN / POSTGRES_TEST_DSN not set")
    return dsn


@pytest_asyncio.fixture(scope="session")
async def migrated_postgres(postgres_dsn: str) -> str:
    """Verify Postgres is reachable and failed_tasks table exists."""
    settings = Settings(database_url=postgres_dsn)
    engine = create_engine(settings)
    try:
        async with engine.connect() as conn:
            await conn.execute(
                text(  # nosemgrep: python.sqlalchemy.security.audit.avoid-sqlalchemy-text.avoid-sqlalchemy-text
                    "SELECT 1 FROM ibex_core.failed_tasks LIMIT 0"
                )
            )
            await conn.commit()
    except Exception as exc:  # noqa: BLE001 — skip when DB or migration missing
        await engine.dispose()
        pytest.skip(f"postgres/migration not available: {exc}")
    await engine.dispose()
    return postgres_dsn
