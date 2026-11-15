"""Real-database proof that ``service_org_session`` pins the tenant role.

Row-level security cannot be mocked. The defect this file guards is a *missing*
role pin, and a fake session cannot produce SQLSTATE 42501: under the owner
login the policies do not apply at all, so the read silently succeeds and
returns every tenant's rows. The shape follows
``packages/billing/store_integration_test.go``: seed as the migration owner, then
connect as ``ibex_runtime`` — a ``NOINHERIT`` capability login that holds no
table grant of its own — so a transaction without ``SET LOCAL ROLE ibex_app``
fails 42501 instead of quietly reading across tenants.

Run it against a migrated database with an asyncpg driver available::

    POSTGRES_TEST_DSN='postgres://ibex:ibex@127.0.0.1:5433/ibex_test?sslmode=disable' \\
        services/memory/.venv/bin/python -m pytest packages/ibex_idempotency/tests -q

The module skips when no DSN is configured or no asyncpg driver is installed:
the package itself depends on SQLAlchemy only, and its own CI environment runs
the unit tests without a database.
"""

from __future__ import annotations

import asyncio
import os
import shutil
import subprocess
from collections.abc import AsyncIterator, Iterator
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import parse_qsl, quote, urlencode, urlsplit, urlunsplit
from uuid import UUID, uuid4

import pytest
import pytest_asyncio
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from ibex_idempotency import KIND_OWNED, KIND_REPLAY, LedgerError, PostgresIdempotencyLedger
from ibex_idempotency.sessions import service_org_session

if not os.getenv("POSTGRES_TEST_DSN"):
    pytest.skip(
        "POSTGRES_TEST_DSN is not set; the RLS role pin needs a real database",
        allow_module_level=True,
    )
pytest.importorskip("asyncpg")

_RUNTIME_LOGIN = "ibex_runtime"
# Must match infra/testing/testcreds/creds.go: the roles and their verifiers are
# cluster-global, so the Go integration packages and this suite provision the
# same values.
_CAPABILITY_PASSWORDS = {
    "IBEX_RUNTIME_DB_PASSWORD": "capability-test-only-runtime",
    "IBEX_WORKER_DB_PASSWORD": "capability-test-only-worker",
    "IBEX_BOOTSTRAP_DB_PASSWORD": "capability-test-only-bootstrap",
    "IBEX_AUTH_DB_PASSWORD": "capability-test-only-auth",
}
_RUNTIME_PASSWORD = _CAPABILITY_PASSWORDS["IBEX_RUNTIME_DB_PASSWORD"]
_SSL_QUERY_KEYS = frozenset({"sslmode", "sslrootcert", "sslcert", "sslkey", "sslcrl"})
_PROVISION_TIMEOUT_SECONDS = 300
_HASH_A = "a" * 64
_HASH_B = "b" * 64
_CLAIM_HASH = "c" * 64


@dataclass(frozen=True, slots=True)
class _Tenants:
    """Two organizations, each with one agent and one ledger row."""

    org_a: UUID
    agent_a: UUID
    org_b: UUID
    agent_b: UUID


def _test_dsn() -> str:
    dsn = os.getenv("POSTGRES_TEST_DSN", "")
    if not dsn:  # pragma: no cover - the module-level skip already covers this
        pytest.skip("POSTGRES_TEST_DSN is not set")
    return dsn


def _with_login(dsn: str, role: str, password: str) -> str:
    """Return ``dsn`` with its userinfo replaced by one capability login."""
    parts = urlsplit(dsn)
    host = parts.hostname or "127.0.0.1"
    port = f":{parts.port}" if parts.port else ""
    netloc = f"{role}:{quote(password, safe='')}@{host}{port}"
    return urlunsplit(parts._replace(netloc=netloc))


def _asyncpg_target(dsn: str) -> tuple[str, dict[str, object]]:
    """Map a libpq-style DSN to an asyncpg URL plus connect args.

    Only what this test needs: the asyncpg scheme and ``sslmode=disable`` (the
    local test DSN). A TLS mode this helper does not model is refused rather
    than silently downgraded.
    """
    parts = urlsplit(dsn)
    query = dict(parse_qsl(parts.query, keep_blank_values=True))
    sslmode = query.get("sslmode")
    connect_args: dict[str, object] = {}
    if sslmode is not None:
        if sslmode.lower() != "disable":
            raise ValueError(f"this test helper supports sslmode=disable only, got {sslmode!r}")
        connect_args["ssl"] = False
    cleaned = [(key, value) for key, value in query.items() if key not in _SSL_QUERY_KEYS]
    url = urlunsplit(("postgresql+asyncpg", parts.netloc, parts.path, urlencode(cleaned), ""))
    return url, connect_args


def _exception_chain(exc: BaseException | None) -> Iterator[BaseException]:
    """Yield ``exc`` and every exception it wraps, following the causal chain."""
    seen: set[int] = set()
    while exc is not None and id(exc) not in seen:
        seen.add(id(exc))
        yield exc
        exc = exc.__cause__ or exc.__context__


def _require_no_permission_denied(exc: BaseException | None, op: str) -> None:
    """Fail on SQLSTATE 42501: that is a missing role pin, not isolation.

    Mirrors ``runtimeconn.RequireNoPermissionDenied`` in the Go suite. The pin is
    what makes the statement legal on a ``NOINHERIT`` login, so a 42501 here
    means the session ran without ``ibex_app`` and must never be read as "this
    tenant has no rows".
    """
    for err in _exception_chain(exc):
        sqlstate = getattr(err, "sqlstate", None) or getattr(
            getattr(err, "orig", None), "sqlstate", None
        )
        if sqlstate == "42501" or "permission denied" in str(err).lower():
            pytest.fail(f"{op}: postgres 42501 permission denied: tenant role not pinned: {err}")


async def _assert_login(engine: AsyncEngine, expected: str) -> None:
    async with engine.connect() as conn:
        current = (await conn.execute(text("SELECT current_user"))).scalar_one()
    if current != expected:  # pragma: no cover - guards a misconfigured DSN
        pytest.fail(f"connected as {current!r}, expected {expected!r}")


def _run_provision_cli(dsn: str) -> subprocess.CompletedProcess[str]:
    """Run ``migrate provision`` (blocking, so it is dispatched to a thread)."""
    repo_root = Path(__file__).resolve().parents[3]
    env = dict(os.environ, POSTGRES_DSN=dsn, **_CAPABILITY_PASSWORDS)
    return subprocess.run(
        ["go", "run", "./infra/migrations/postgres/cmd/migrate", "-command", "provision"],
        cwd=repo_root,
        env=env,
        capture_output=True,
        text=True,
        timeout=_PROVISION_TIMEOUT_SECONDS,
        check=False,
    )


async def _provision_runtime_login(dsn: str) -> None:
    """Give the capability logins a verifier via the repo's provisioning CLI.

    Migration 000064 creates ``ibex_runtime`` with no password and
    ``CONNECTION LIMIT 0``, so a non-owner login has to be provisioned before it
    can connect. ``migrate provision`` is the same routine the Go integration
    packages call (``pgprovision.CapabilityLogins``).
    """
    if shutil.which("go") is None:  # pragma: no cover - tooling failure path
        pytest.skip("go is required to provision the ibex_runtime login (migrate provision)")
    result = await asyncio.to_thread(_run_provision_cli, dsn)
    if result.returncode != 0:  # pragma: no cover - environment failure path
        pytest.fail(f"migrate provision failed: {result.stderr.strip() or result.stdout.strip()}")


async def _runtime_engine() -> AsyncEngine:
    """Return an engine that logs in as ``ibex_runtime``, provisioning it once."""
    dsn = _test_dsn()
    url, connect_args = _asyncpg_target(_with_login(dsn, _RUNTIME_LOGIN, _RUNTIME_PASSWORD))
    engine = create_async_engine(url, connect_args=connect_args)
    try:
        await _assert_login(engine, _RUNTIME_LOGIN)
        return engine
    except (SQLAlchemyError, OSError):
        await engine.dispose()
    await _provision_runtime_login(dsn)
    engine = create_async_engine(url, connect_args=connect_args)
    try:
        await _assert_login(engine, _RUNTIME_LOGIN)
    except BaseException:
        await engine.dispose()
        raise
    return engine


@pytest_asyncio.fixture
async def owner_engine() -> AsyncIterator[AsyncEngine]:
    """The migration owner (superuser), used only to seed fixtures."""
    url, connect_args = _asyncpg_target(_test_dsn())
    engine = create_async_engine(url, connect_args=connect_args)
    try:
        await _assert_login(engine, "ibex")
        yield engine
    finally:
        await engine.dispose()


@pytest_asyncio.fixture
async def runtime_factory() -> AsyncIterator[async_sessionmaker[AsyncSession]]:
    """A session factory that logs in as ``ibex_runtime``, never the owner."""
    engine = await _runtime_engine()
    try:
        yield async_sessionmaker(engine, expire_on_commit=False)
    finally:
        await engine.dispose()


async def _seed(owner_engine: AsyncEngine) -> _Tenants:
    """Seed two tenants with one ledger row each, as the owner."""
    tenants = _Tenants(uuid4(), uuid4(), uuid4(), uuid4())
    async with owner_engine.begin() as conn:
        for org, agent, label in (
            (tenants.org_a, tenants.agent_a, "a"),
            (tenants.org_b, tenants.agent_b, "b"),
        ):
            await conn.execute(
                text(
                    "INSERT INTO ibex_core.organizations (id, name, slug, status)"
                    " VALUES (:id, :name, :slug, 'active')"
                ),
                {"id": org, "name": f"ledger pin {label}", "slug": f"ledger-pin-{org}"},
            )
            await conn.execute(
                text(
                    "INSERT INTO ibex_core.agents (id, org_id, name, slug, status)"
                    " VALUES (:id, :org, :name, :slug, 'active')"
                ),
                {"id": agent, "org": org, "name": f"pin agent {label}", "slug": f"pin-{agent}"},
            )
        await conn.execute(
            text(
                """
                INSERT INTO ibex_core.idempotency_ledger
                  (organization_id, agent_id, dedupe_key, request_hash, state, lease_expires_at)
                VALUES (:org, :agent, 'seed-a', :hash, 'claimed', NOW() + interval '120 seconds')
                """
            ),
            {"org": tenants.org_a, "agent": tenants.agent_a, "hash": _HASH_A},
        )
        await conn.execute(
            text(
                """
                INSERT INTO ibex_core.idempotency_ledger
                  (organization_id, agent_id, dedupe_key, request_hash, state,
                   status_code, response_payload)
                VALUES (:org, :agent, 'seed-b', :hash, 'finalized', 200, :payload)
                """
            ),
            {
                "org": tenants.org_b,
                "agent": tenants.agent_b,
                "hash": _HASH_B,
                "payload": b'{"seeded":"b"}',
            },
        )
    return tenants


@pytest.mark.asyncio
async def test_service_org_session_pins_ibex_app_and_hides_the_other_tenant(
    runtime_factory: async_sessionmaker[AsyncSession],
    owner_engine: AsyncEngine,
) -> None:
    """The pin is what makes the org GUC effective for a capability login.

    Before the pin the transaction ran as ``ibex_runtime``: that login holds no
    grant on ``ibex_core.idempotency_ledger``, so the read failed 42501 instead
    of being scoped. With the pin the same read returns org A's row and only
    org A's row, and an explicit filter for org B returns nothing.
    """
    tenants = await _seed(owner_engine)

    try:
        async with service_org_session(runtime_factory, str(tenants.org_a)) as session:
            current_user = (await session.execute(text("SELECT current_user"))).scalar_one()
            visible = (
                await session.execute(
                    text(
                        "SELECT dedupe_key FROM ibex_core.idempotency_ledger ORDER BY dedupe_key"
                    )
                )
            ).scalars()
            other = (
                await session.execute(
                    text(
                        "SELECT count(*) FROM ibex_core.idempotency_ledger"
                        " WHERE organization_id = :org"
                    ),
                    {"org": tenants.org_b},
                )
            ).scalar_one()
    except SQLAlchemyError as exc:
        _require_no_permission_denied(exc, "service_org_session read")
        raise

    assert current_user == "ibex_app", "the transaction must run as the RLS-enforcing role"
    assert list(visible) == ["seed-a"], "the pinned tenant must see exactly its own row"
    assert other == 0, "RLS must hide the other tenant behind an explicit filter"


@pytest.mark.asyncio
async def test_default_ledger_scopes_claim_and_replay_within_one_tenant(
    runtime_factory: async_sessionmaker[AsyncSession],
    owner_engine: AsyncEngine,
) -> None:
    """The package default scope is the pinned one, end to end.

    ``PostgresIdempotencyLedger`` with no injected scope is the path a new
    consumer gets. It must claim as ``ibex_app`` (a 42501 here is the missing
    pin), replay only its own tenant's finalized row, and treat another tenant's
    identical dedupe key as absent rather than replaying it.
    """
    tenants = await _seed(owner_engine)
    ledger = PostgresIdempotencyLedger(runtime_factory)

    try:
        claimed = await ledger.claim(
            org_id=tenants.org_a,
            agent_id=tenants.agent_a,
            key="pinned-a",
            request_hash=_CLAIM_HASH,
        )
        replay = await ledger.claim(
            org_id=tenants.org_b,
            agent_id=tenants.agent_b,
            key="seed-b",
            request_hash=_HASH_B,
        )
        cross_tenant = await ledger.claim(
            org_id=tenants.org_a,
            agent_id=tenants.agent_a,
            key="seed-b",
            request_hash=_HASH_B,
        )
    except LedgerError as exc:
        _require_no_permission_denied(exc, "default ledger claim")
        raise

    assert claimed.kind == KIND_OWNED
    assert replay.kind == KIND_REPLAY
    assert replay.status == 200, "org B must replay its own finalized row"
    assert cross_tenant.kind == KIND_OWNED, "org B's row must be invisible to org A"
