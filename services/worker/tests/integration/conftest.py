"""Integration test fixtures (real Redis broker + result backend)."""

from __future__ import annotations

import os
import socket
import sys
from collections.abc import AsyncIterator, Iterator
from pathlib import Path
from urllib.parse import urlparse

import pytest
import pytest_asyncio
import redis as redis_sync
from celery import Celery
from celery.contrib.testing.worker import start_worker
from redis.exceptions import RedisError
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.celery_app import create_celery_app
from app.config import Settings, get_settings
from app.db import create_engine, create_session_factory
from app.observability import reset_observability_for_tests
from app.tasks import lifecycle_erasure
from tests.integration import lifecycle_erasure_harness as erasure_harness

_REPO_ROOT = Path(__file__).resolve().parents[4]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from infra.testing.pgcapability import (
    WORKER_LOGIN,
    capability_dsn,
    provision_capability_logins,
)

_REDIS_BASE = os.environ.get("REDIS_URL", "redis://127.0.0.1:6379/0")
_QUEUE_DB = int(os.environ.get("REDIS_DB_QUEUE", "1"))
_RESULTS_DB = int(os.environ.get("REDIS_DB_RESULTS", "3"))
_FORBIDDEN_FLUSH_DB = 0
_INTEGRATION_OPT_IN_ENV = "IBEX_WORKER_INTEGRATION_TESTS"
_LOCAL_REDIS_HOSTS = frozenset({"127.0.0.1", "localhost", "::1"})
_POSTGRES_TEST_DSN_ENV = "POSTGRES_TEST_DSN"


def _assert_destructive_postgres_opt_in() -> None:
    if os.environ.get(_POSTGRES_TEST_DSN_ENV):
        return
    pytest.fail(
        f"Worker integration tests TRUNCATE ibex_core.failed_tasks. "
        f"Set {_POSTGRES_TEST_DSN_ENV} to a dedicated test database."
    )


def _truthy_env(name: str) -> bool:
    return os.environ.get(name, "").strip().lower() in {"1", "true", "yes"}


def _redis_db_index(url: str) -> int:
    parsed = urlparse(url)
    if parsed.scheme in {"redis", "rediss"}:
        return int(parsed.path.lstrip("/") or "0")
    if parsed.scheme == "redis+socket":
        query = dict(part.split("=", 1) for part in parsed.query.split("&") if "=" in part)
        return int(query.get("virtual_host", "0"))
    msg = f"unsupported Redis URL for integration flush guard: {url!r}"
    raise ValueError(msg)


def _assert_integration_redis_opt_in() -> None:
    if _truthy_env("CI") or _truthy_env(_INTEGRATION_OPT_IN_ENV):
        return
    pytest.fail(
        f"Worker integration tests flush dedicated Redis DBs. "
        f"Set {_INTEGRATION_OPT_IN_ENV}=1 or run under CI before executing them."
    )


def _assert_local_redis_base(redis_url: str) -> None:
    parsed = urlparse(redis_url)
    host = (parsed.hostname or "").lower()
    if host in _LOCAL_REDIS_HOSTS:
        return
    pytest.fail(
        f"integration tests refuse non-local Redis endpoint {redis_url!r}; "
        f"use 127.0.0.1/localhost or set {_INTEGRATION_OPT_IN_ENV}=1 to opt in"
    )


def _assert_dedicated_worker_redis_urls(settings: Settings) -> None:
    _assert_integration_redis_opt_in()
    if not _truthy_env(_INTEGRATION_OPT_IN_ENV):
        _assert_local_redis_base(settings.redis_url)
    broker_url = settings.resolved_broker_url
    result_url = settings.resolved_result_backend
    broker_db = _redis_db_index(broker_url)
    result_db = _redis_db_index(result_url)
    if broker_db == _FORBIDDEN_FLUSH_DB:
        pytest.fail(f"broker URL must not target cache DB {_FORBIDDEN_FLUSH_DB}: {broker_url}")
    if result_db == _FORBIDDEN_FLUSH_DB:
        pytest.fail(f"result URL must not target cache DB {_FORBIDDEN_FLUSH_DB}: {result_url}")
    if broker_db == result_db:
        pytest.fail(
            f"broker and result backends must use separate DB indices (both {broker_db})"
        )


@pytest.fixture(scope="session")
def require_redis() -> str:
    client = redis_sync.Redis.from_url(
        _REDIS_BASE,
        socket_connect_timeout=0.5,
        socket_timeout=0.5,
    )
    try:
        client.ping()
    except (RedisError, OSError, TimeoutError) as exc:
        pytest.skip(f"Redis not available at {_REDIS_BASE}: {exc}")
    finally:
        client.close()
    return _REDIS_BASE


@pytest.fixture(scope="session")
def require_postgres(postgres_dsn: str) -> str:
    return postgres_dsn


@pytest_asyncio.fixture
async def owner_factory(postgres_dsn: str) -> AsyncIterator[async_sessionmaker[AsyncSession]]:
    """Session factory for the migration owner login (seeding and assertions)."""
    engine = create_engine(Settings(database_url=postgres_dsn))
    try:
        yield create_session_factory(engine)
    finally:
        await engine.dispose()


@pytest_asyncio.fixture
async def worker_factory(
    capability_worker_dsn: str,
) -> AsyncIterator[async_sessionmaker[AsyncSession]]:
    """Session factory that logs in as ``ibex_worker`` (never the owner)."""
    engine = create_engine(Settings(database_url=capability_worker_dsn))
    factory = create_session_factory(engine)
    try:
        async with factory() as session:
            current_user = (
                await session.execute(
                    text(  # nosemgrep: python.sqlalchemy.security.audit.avoid-sqlalchemy-text.avoid-sqlalchemy-text
                        "SELECT current_user"
                    )
                )
            ).scalar_one()
        assert current_user == "ibex_worker", current_user
        assert current_user != "ibex", "owner login would bypass RLS"
        yield factory
    finally:
        await engine.dispose()


@pytest.fixture(scope="session")
def capability_worker_dsn(postgres_dsn: str) -> str:
    """Provision and return a DSN that logs in as ``ibex_worker``.

    The capability logins are created by migration 000064 with no password and
    ``CONNECTION LIMIT 0``, so a test that needs a non-superuser login must run
    the provisioning command first. ``migrate provision`` is the Go CLI for the
    same routine the Go integration packages call.
    """
    try:
        provision_capability_logins(postgres_dsn, _REPO_ROOT)
    except RuntimeError as exc:
        pytest.fail(str(exc))
    return capability_dsn(postgres_dsn, WORKER_LOGIN)


def _free_tcp_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


@pytest.fixture
def integration_settings(
    require_redis: str,
    require_postgres: str,
    capability_worker_dsn: str,
) -> Iterator[Settings]:
    """Settings for the worker under test: the ``ibex_worker`` login.

    ``_on_worker_process_init`` asserts this login and fails the process on the
    owner, so the app under test boots on ``capability_worker_dsn``. The test
    itself keeps ``postgres_dsn`` (the owner) for seeding, assertions, and
    destructive helpers such as ``TRUNCATE``.
    """
    get_settings.cache_clear()
    reset_observability_for_tests()
    previous_dsn = os.environ.get("POSTGRES_DSN")
    os.environ["REDIS_URL"] = require_redis
    os.environ["POSTGRES_TEST_DSN"] = require_postgres
    os.environ["POSTGRES_DSN"] = capability_worker_dsn
    os.environ["IBEX_WORKER_METRICS_PORT"] = str(_free_tcp_port())
    settings = get_settings()
    try:
        yield settings
    finally:
        if previous_dsn is None:
            os.environ.pop("POSTGRES_DSN", None)
        else:
            os.environ["POSTGRES_DSN"] = previous_dsn
        get_settings.cache_clear()
        reset_observability_for_tests()


@pytest.fixture
def celery_app(integration_settings: Settings) -> Celery:
    return create_celery_app(integration_settings)


@pytest.fixture
def eager_celery_app(integration_settings: Settings) -> Celery:
    """Eager Celery app for dead-letter tests (synchronous retries)."""
    from app.observability import _on_worker_process_init, _on_worker_ready

    app = create_celery_app(integration_settings)
    app.conf.update(
        task_always_eager=True,
        task_store_eager_result=True,
    )
    _on_worker_process_init()
    _on_worker_ready()
    return app


@pytest.fixture(autouse=True)
def flush_worker_redis_dbs(integration_settings: Settings) -> Iterator[None]:
    """Flush only broker/result DBs — never DB 0 (shared cache)."""
    _assert_dedicated_worker_redis_urls(integration_settings)
    clients = [
        redis_sync.Redis.from_url(integration_settings.resolved_broker_url),
        redis_sync.Redis.from_url(integration_settings.resolved_result_backend),
    ]
    for client in clients:
        client.flushdb()
    yield
    for client in clients:
        client.flushdb()
        client.close()


@pytest.fixture
def worker(celery_app: Celery) -> Iterator[object]:
    with start_worker(
        celery_app,
        perform_ping_check=False,
        concurrency=1,
        pool="solo",
        loglevel="WARNING",
    ) as worker_instance:
        yield worker_instance


@pytest.fixture
async def truncate_failed_tasks(postgres_dsn: str) -> None:
    """Truncate the dead-letter table as the owner.

    ``ibex_worker`` holds no grant on ``ibex_core.failed_tasks`` (and its
    ``SELECT`` is revoked from ``ibex_app``), so the destructive helper must use
    the owner DSN, not the app-under-test settings.
    """
    _assert_destructive_postgres_opt_in()
    engine = create_engine(Settings(database_url=postgres_dsn))
    async with engine.begin() as conn:
        await conn.execute(
            text(  # nosemgrep: python.sqlalchemy.security.audit.avoid-sqlalchemy-text.avoid-sqlalchemy-text
                "TRUNCATE ibex_core.failed_tasks"
            )
        )
    await engine.dispose()


@pytest.fixture(scope="session")
def clickhouse_http_dsn() -> str:
    """The ClickHouse HTTP DSN, skipping the suite when it is unreachable."""
    return erasure_harness.require_clickhouse(erasure_harness.CH_DSN)


@pytest.fixture
async def clean_erasure_worklist(
    owner_factory: async_sessionmaker[AsyncSession],
) -> None:
    """Empty the erasure worklist before a memory-erasure test.

    The consumer is a global sweep: it claims whatever is claimable, across
    tenants, by design. A row another suite (or an earlier run of this one) left
    pending would therefore be claimed and make the per-run tallies meaningless.
    This suite owns these three tables for the duration of a run, which is why it
    runs serially (``-p 1``) against the shared test database.
    """
    async with owner_factory() as session, session.begin():
        for statement in erasure_harness.CLEANUP_STATEMENTS:
            await session.execute(erasure_harness.sql_text(statement))


@pytest.fixture
def object_store(monkeypatch: pytest.MonkeyPatch) -> erasure_harness.FakeObjectStore:
    """Replace the object-store client with a fake this suite can assert on.

    The delete runs in the staging module and the settle re-check runs in the
    sweep module; each reads its own imported name, so both are patched.
    """
    fake = erasure_harness.FakeObjectStore()
    monkeypatch.setattr(lifecycle_erasure.staging, "delete_uri", fake.delete)
    monkeypatch.setattr(lifecycle_erasure.staging, "object_exists", fake.exists)
    monkeypatch.setattr(lifecycle_erasure.sweep, "object_exists", fake.exists)
    return fake


@pytest.fixture
def erasure_env(
    owner_factory: async_sessionmaker[AsyncSession],
    capability_worker_dsn: str,
    require_redis: str,
    clickhouse_http_dsn: str,
) -> erasure_harness.ErasureEnv:
    """The real dependencies one memory-erasure consumer run needs."""
    return erasure_harness.ErasureEnv(
        owner=owner_factory,
        dsn=capability_worker_dsn,
        redis_url=require_redis,
        ch_dsn=clickhouse_http_dsn,
    )


@pytest.fixture
def no_ambient_clickhouse(monkeypatch: pytest.MonkeyPatch) -> None:
    """Clear the ClickHouse env fallbacks for a memory-erasure test.

    The consumer treats ``CLICKHOUSE_DSN`` in the environment as "ClickHouse is
    deployed", so a suite that controls reachability through ``Settings`` must
    clear it first — otherwise a developer or CI environment with the variable
    set silently turns the unreachable-store case into a reachable one.
    """
    monkeypatch.delenv("CLICKHOUSE_DSN", raising=False)
    monkeypatch.delenv("IBEX_WORKER_CLICKHOUSE_DSN", raising=False)


@pytest.fixture
async def harness(
    erasure_env: erasure_harness.ErasureEnv,
    clean_erasure_worklist: None,
    no_ambient_clickhouse: None,
) -> erasure_harness.Harness:
    """Seed, run and read back the memory-erasure consumer."""
    # Both dependencies are preconditions, not values.
    del clean_erasure_worklist, no_ambient_clickhouse
    return erasure_harness.Harness(env=erasure_env)
