"""Shared seeding helpers for the worker tenant-pinning suite.

A test that runs as the migration owner (``ibex``, superuser) bypasses RLS and
needs no role, so it cannot prove that ``SET LOCAL ROLE`` is doing anything.
Every case in ``test_worker_tenant_pinning_*_postgres.py`` connects through the
``ibex_worker`` fixture -- a ``NOINHERIT`` capability login with no implicit
tenant or purge privileges -- so a missing pin fails with SQLSTATE 42501 instead
of silently succeeding.

Red evidence for each case is recorded in the PR: removing the corresponding
``SET LOCAL ROLE`` makes it fail with ``permission denied``.

The session factories (``owner_factory``, ``worker_factory``) live in
``conftest.py``; this module holds only the plain helpers the split test modules
share.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from uuid import UUID, uuid4

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.budget_ledger import BudgetClaimRequest
from app.config import Settings
from app.db import (
    app_org_scope,
    app_probe_scope,
    create_engine,
    create_session_factory,
)
from app.idempotency_ledger import PostgresIdempotencyLedger
from app.repositories.failed_tasks import FailedTaskRecord


def sql_text(statement: str):
    return text(  # nosemgrep: python.sqlalchemy.security.audit.avoid-sqlalchemy-text.avoid-sqlalchemy-text
        statement
    )


async def assert_worker_login(dsn: str) -> None:
    """Fail unless the DSN really authenticates as the capability login."""
    engine = create_engine(Settings(database_url=dsn))
    try:
        factory = create_session_factory(engine)
        async with factory() as session:
            current_user = (await session.execute(sql_text("SELECT current_user"))).scalar_one()
    finally:
        await engine.dispose()
    assert current_user == "ibex_worker", current_user
    assert current_user != "ibex", "owner login would bypass RLS"


async def seed_org(
    factory: async_sessionmaker[AsyncSession],
    org_id: UUID,
    *,
    job_id: UUID | None = None,
) -> None:
    async with factory() as session, session.begin():
        await session.execute(
            sql_text("INSERT INTO ibex_core.organizations (id, name, slug) VALUES (:id, :name, :slug)"),
            {"id": org_id, "name": f"Pin {org_id.hex[:8]}", "slug": f"pin-{org_id.hex[:12]}"},
        )
        if job_id is not None:
            await session.execute(
                sql_text(
                    """
                    INSERT INTO ibex_core.org_deletion_jobs (id, org_id, status)
                    VALUES (:id, :org_id, 'pending')
                    """
                ),
                {"id": job_id, "org_id": org_id},
            )


async def seed_period(
    factory: async_sessionmaker[AsyncSession],
    org_id: UUID,
    period_id: UUID,
    *,
    spent_cents: int = 0,
) -> None:
    async with factory() as session, session.begin():
        await session.execute(
            sql_text(
                """
                INSERT INTO ibex_billing.budget_periods
                    (id, org_id, period_start, period_end, cap_cents,
                     spent_cents_cached, enforcement_mode)
                VALUES (:id, :org_id, NOW() - interval '1 day', NOW() + interval '1 day',
                        100000, :spent, 'hard_cap')
                """
            ),
            {"id": period_id, "org_id": org_id, "spent": spent_cents},
        )


async def seed_tenant_rows(
    factory: async_sessionmaker[AsyncSession],
    org_id: UUID,
    *,
    tag: str,
) -> tuple[UUID, UUID]:
    """Seed one agent + one user + one invite for ``org_id``; return user/agent ids."""
    user_id = uuid4()
    agent_id = uuid4()
    async with factory() as session, session.begin():
        await session.execute(
            sql_text(
                """
                INSERT INTO ibex_core.agents (id, org_id, name, slug)
                VALUES (:id, :org_id, :name, :slug)
                """
            ),
            {"id": agent_id, "org_id": org_id, "name": f"agent-{tag}", "slug": f"agent-{tag}"},
        )
        await session.execute(
            sql_text(
                """
                INSERT INTO ibex_core.users (id, org_id, email, name)
                VALUES (:id, :org_id, :email, :name)
                """
            ),
            {
                "id": user_id,
                "org_id": org_id,
                "email": f"user-{tag}@example.test",
                "name": f"user-{tag}",
            },
        )
        await session.execute(
            sql_text(
                """
                INSERT INTO ibex_core.organization_invites
                    (org_id, email, token_hash, expires_at)
                VALUES (:org_id, :email, :token_hash, NOW() + interval '1 day')
                """
            ),
            {
                "org_id": org_id,
                "email": f"invite-{tag}@example.test",
                "token_hash": f"hash-{tag}",
            },
        )
    return user_id, agent_id


async def count_rows(
    factory: async_sessionmaker[AsyncSession], statement: str, **params: object
) -> int:
    async with factory() as session:
        return int((await session.execute(sql_text(statement), params)).scalar_one())


async def fetch_one(
    factory: async_sessionmaker[AsyncSession], statement: str, **params: object
):
    async with factory() as session:
        return (await session.execute(sql_text(statement), params)).one()


async def fetch_all(
    factory: async_sessionmaker[AsyncSession], statement: str, **params: object
):
    async with factory() as session:
        return (await session.execute(sql_text(statement), params)).all()


def sqlstate(exc: BaseException | None) -> str | None:
    return getattr(getattr(exc, "orig", None), "sqlstate", None)


async def seed_rate_card(
    factory: async_sessionmaker[AsyncSession],
    org_id: UUID,
    card_id: UUID,
) -> None:
    prices = json.dumps(
        [
            {
                "provider": "openai",
                "model_pattern": "gpt-4o*",
                "input_cents_per_1k": 10,
                "output_cents_per_1k": 30,
            }
        ]
    )
    async with factory() as session, session.begin():
        await session.execute(
            sql_text(
                """
                INSERT INTO ibex_billing.rate_cards (id, org_id, name, status)
                VALUES (:id, :org, :name, 'published')
                """
            ),
            {"id": card_id, "org": org_id, "name": f"card-{card_id.hex[:8]}"},
        )
        await session.execute(
            sql_text(
                """
                INSERT INTO ibex_billing.rate_card_versions
                    (rate_card_id, org_id, version, prices)
                VALUES (:id, :org, 1, CAST(:prices AS jsonb))
                """
            ),
            {"id": card_id, "org": org_id, "prices": prices},
        )


async def seed_capture_policy(
    factory: async_sessionmaker[AsyncSession],
    org_id: UUID,
    *,
    agent_id: UUID | None = None,
    mode: str = "metadata_only",
    priority: int = 0,
) -> None:
    """Seed one capture policy row; ``agent_id=None`` is the org default."""
    async with factory() as session, session.begin():
        await session.execute(
            sql_text(
                """
                INSERT INTO ibex_core.org_capture_policies (org_id, agent_id, mode, priority)
                VALUES (:org, :agent, :mode, :priority)
                """
            ),
            {"org": org_id, "agent": agent_id, "mode": mode, "priority": priority},
        )


@dataclass(frozen=True, slots=True)
class SessionSeed:
    """The rows a session-store case needs before it can pin anything."""

    org_id: UUID
    agent_id: UUID
    session_id: UUID
    turn: int = 5


async def seed_session(
    factory: async_sessionmaker[AsyncSession], seed: SessionSeed
) -> None:
    async with factory() as session, session.begin():
        await session.execute(
            sql_text(
                """
                INSERT INTO ibex_core.sessions (
                    id, org_id, agent_id, status, model, provider, last_extracted_turn
                ) VALUES (
                    :id, :org, :agent, 'completed', 'gpt-4o-mini', 'openai', :turn
                )
                """
            ),
            {
                "id": seed.session_id,
                "org": seed.org_id,
                "agent": seed.agent_id,
                "turn": seed.turn,
            },
        )


def budget_request(org_id: UUID, agent_id: UUID, *, key: str) -> BudgetClaimRequest:
    return BudgetClaimRequest(
        org_id=org_id,
        agent_id=agent_id,
        key=key,
        request_hash="a" * 64,
        provider="openai",
        model="gpt-4o-mini",
        input_tokens=100,
        output_tokens=200,
    )


def failed_record(task_id: str) -> FailedTaskRecord:
    return FailedTaskRecord(
        task_name="ibex.worker.maintenance.always_fail",
        task_id=task_id,
        args=[],
        kwargs={},
        exception_type="RuntimeError",
        exception_message="pinned dead letter",
        traceback_text="traceback",
        retry_count=3,
        org_id=None,
    )


def pinned_ledger(
    factory: async_sessionmaker[AsyncSession],
) -> PostgresIdempotencyLedger:
    return PostgresIdempotencyLedger(
        factory,
        session_scope=app_org_scope(factory),
        probe_scope=app_probe_scope(factory),
    )
