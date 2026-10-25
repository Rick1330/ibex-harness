"""Conformance: the shared Python ledger on a real PostgreSQL ledger table.

These tests pin the ``request-idempotency-core.v1`` semantics that the Go ledger
(proxy/worker) and the Python ledger (worker enqueue + memory create) must both
honor on ``ibex_core.idempotency_ledger``:

* a fresh claim is ``owned``; ``finalize`` makes it replayable
* a reused key with a different request hash is a ``conflict``
* a live claim reports ``in_progress`` with a positive retry hint
* an expired lease may be reclaimed; the previous owner is fenced off
* ``release`` deletes the claim and the key becomes claimable again
* the row is scoped to ``(org, agent, key)`` and isolated by RLS
* a crash (claim committed, never finalized) recovers via lease reclaim
"""

from __future__ import annotations

import asyncio
from uuid import UUID, uuid4

import pytest
from ibex_idempotency import (
    KIND_CONFLICT,
    KIND_IN_PROGRESS,
    KIND_OWNED,
    KIND_REPLAY,
    LedgerConflictError,
    PostgresIdempotencyLedger,
)
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker


def _hash(seed: str) -> str:
    return (seed * 64)[:64]


@pytest.mark.asyncio
async def test_claim_finalize_replay(ledger, principal) -> None:
    org_id, agent_id = principal
    outcome = await ledger.claim(org_id=org_id, agent_id=agent_id, key="k", request_hash=_hash("a"))
    assert outcome.kind == KIND_OWNED
    assert outcome.claim is not None

    await ledger.finalize(outcome.claim, status=201, response=b'{"id":"m1"}')

    replay = await ledger.claim(org_id=org_id, agent_id=agent_id, key="k", request_hash=_hash("a"))
    assert replay.kind == KIND_REPLAY
    assert replay.status == 201
    assert replay.response == b'{"id":"m1"}'


@pytest.mark.asyncio
async def test_finalize_is_idempotent_fenced(ledger, principal) -> None:
    org_id, agent_id = principal
    outcome = await ledger.claim(
        org_id=org_id, agent_id=agent_id, key="k2", request_hash=_hash("a")
    )
    assert outcome.claim is not None
    await ledger.finalize(outcome.claim, status=200, response=b"{}")
    with pytest.raises(LedgerConflictError):
        await ledger.finalize(outcome.claim, status=200, response=b"{}")


@pytest.mark.asyncio
async def test_reused_key_with_different_body_conflicts(ledger, principal) -> None:
    org_id, agent_id = principal
    await ledger.claim(org_id=org_id, agent_id=agent_id, key="k3", request_hash=_hash("a"))
    outcome = await ledger.claim(
        org_id=org_id, agent_id=agent_id, key="k3", request_hash=_hash("b")
    )
    assert outcome.kind == KIND_CONFLICT


@pytest.mark.asyncio
async def test_live_claim_reports_in_progress(ledger, principal) -> None:
    org_id, agent_id = principal
    await ledger.claim(org_id=org_id, agent_id=agent_id, key="k4", request_hash=_hash("a"))
    outcome = await ledger.claim(
        org_id=org_id, agent_id=agent_id, key="k4", request_hash=_hash("a")
    )
    assert outcome.kind == KIND_IN_PROGRESS
    assert outcome.retry_after is not None
    assert outcome.retry_after >= 1


@pytest.mark.asyncio
async def test_release_reopens_key(ledger, principal) -> None:
    org_id, agent_id = principal
    outcome = await ledger.claim(
        org_id=org_id, agent_id=agent_id, key="k5", request_hash=_hash("a")
    )
    assert outcome.claim is not None
    await ledger.release(outcome.claim)
    with pytest.raises(LedgerConflictError):
        await ledger.release(outcome.claim)
    reclaimed = await ledger.claim(
        org_id=org_id, agent_id=agent_id, key="k5", request_hash=_hash("a")
    )
    assert reclaimed.kind == KIND_OWNED


@pytest.mark.asyncio
async def test_crash_replay_recovers_after_lease_expiry(
    session_factory: async_sessionmaker[AsyncSession], principal
) -> None:
    org_id, agent_id = principal
    # A short lease models a worker that crashed mid-flight.
    crashed = PostgresIdempotencyLedger(session_factory, lease_seconds=1.0)
    claim = await crashed.claim(
        org_id=org_id, agent_id=agent_id, key="crash", request_hash=_hash("c")
    )
    assert claim.kind == KIND_OWNED
    assert claim.claim is not None
    # No finalize: the process "dies" here. A restarted ledger reclaims the lease.
    await asyncio.sleep(1.5)

    restarted = PostgresIdempotencyLedger(session_factory, lease_seconds=30.0)
    recovered = await restarted.claim(
        org_id=org_id, agent_id=agent_id, key="crash", request_hash=_hash("c")
    )
    assert recovered.kind == KIND_OWNED
    assert recovered.claim is not None
    assert recovered.claim.version > claim.claim.version

    # The stale owner can no longer finalize; the new owner can, and replay works.
    with pytest.raises(LedgerConflictError):
        await crashed.finalize(claim.claim, status=200, response=b"stale")
    await restarted.finalize(recovered.claim, status=200, response=b'{"recovered":true}')
    replay = await restarted.claim(
        org_id=org_id, agent_id=agent_id, key="crash", request_hash=_hash("c")
    )
    assert replay.kind == KIND_REPLAY
    assert replay.response == b'{"recovered":true}'


@pytest.mark.asyncio
async def test_key_scope_is_per_org(ledger, principal, second_principal) -> None:
    org_a, agent_a = principal
    org_b, agent_b = second_principal
    hash_a = _hash("a")

    first = await ledger.claim(org_id=org_a, agent_id=agent_a, key="shared", request_hash=hash_a)
    second = await ledger.claim(org_id=org_b, agent_id=agent_b, key="shared", request_hash=hash_a)
    assert first.kind == KIND_OWNED
    assert second.kind == KIND_OWNED


@pytest.mark.asyncio
async def test_rls_hides_other_org_rows(
    session_factory: async_sessionmaker[AsyncSession], ledger, principal, second_principal
) -> None:
    org_a, agent_a = principal
    org_b, _ = second_principal
    await ledger.claim(org_id=org_a, agent_id=agent_a, key="rls", request_hash=_hash("a"))

    async with session_factory() as session, session.begin():
        # Assume the non-superuser role so FORCE RLS is enforced; the test DSN
        # connects as the superuser, which would otherwise bypass the policy.
        await session.execute(
            text(  # nosemgrep: python.sqlalchemy.security.audit.avoid-sqlalchemy-text.avoid-sqlalchemy-text
                "SET LOCAL ROLE ibex_app"
            )
        )
        await session.execute(
            text(  # nosemgrep: python.sqlalchemy.security.audit.avoid-sqlalchemy-text.avoid-sqlalchemy-text
                "SELECT set_config('app.current_org_id', :org, true)"
            ),
            {"org": str(org_b)},
        )
        visible = (
            await session.execute(
                text(  # nosemgrep: python.sqlalchemy.security.audit.avoid-sqlalchemy-text.avoid-sqlalchemy-text
                    "SELECT count(*) FROM ibex_core.idempotency_ledger "
                    "WHERE organization_id = :org_a"
                ),
                {"org_a": org_a},
            )
        ).scalar_one()
    assert visible == 0


@pytest.mark.asyncio
async def test_unknown_agent_fails_closed(ledger, principal) -> None:
    org_id, _ = principal
    unknown_agent = uuid4()

    from ibex_idempotency import LedgerValidationError  # noqa: PLC0415 — narrow import mirrors neighboring tests

    with pytest.raises(LedgerValidationError):
        await ledger.claim(org_id=org_id, agent_id=unknown_agent, key="fk", request_hash=_hash("a"))


@pytest.mark.asyncio
async def test_agent_scope_is_part_of_key(ledger, session_factory, principal) -> None:
    org_id, agent_id = principal
    async with session_factory() as session, session.begin():
        await session.execute(
            text(  # nosemgrep: python.sqlalchemy.security.audit.avoid-sqlalchemy-text.avoid-sqlalchemy-text
                "SELECT set_config('app.is_service_account', 'true', true)"
            )
        )
        other_agent: UUID = (
            await session.execute(
                text(  # nosemgrep: python.sqlalchemy.security.audit.avoid-sqlalchemy-text.avoid-sqlalchemy-text
                    "INSERT INTO ibex_core.agents (org_id, name, slug) "
                    "VALUES (:org, 'second', :slug) RETURNING id"
                ),
                {"org": org_id, "slug": f"second-{org_id.hex[:8]}"},
            )
        ).scalar_one()

    first = await ledger.claim(
        org_id=org_id, agent_id=agent_id, key="agent-scope", request_hash=_hash("a")
    )
    second = await ledger.claim(
        org_id=org_id, agent_id=other_agent, key="agent-scope", request_hash=_hash("a")
    )
    assert first.kind == KIND_OWNED
    assert second.kind == KIND_OWNED
