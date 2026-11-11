"""Integration test fixtures (real Redis broker + result backend)."""

from __future__ import annotations

import os
import shutil
import socket
import subprocess
from collections.abc import Iterator
from pathlib import Path
from urllib.parse import quote, urlparse, urlsplit, urlunsplit

import pytest
import redis as redis_sync
from celery import Celery
from celery.contrib.testing.worker import start_worker
from redis.exceptions import RedisError
from sqlalchemy import text

from app.celery_app import create_celery_app
from app.config import Settings, get_settings
from app.db import create_engine
from app.observability import reset_observability_for_tests

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


# Capability-login secrets. These must match infra/testing/testcreds/creds.go:
# the roles and their verifiers are cluster-global, so the Go integration
# packages and this Python suite have to provision the same values.
_CAPABILITY_PASSWORDS = {
    "IBEX_RUNTIME_DB_PASSWORD": "capability-test-only-runtime",
    "IBEX_WORKER_DB_PASSWORD": "capability-test-only-worker",
    "IBEX_BOOTSTRAP_DB_PASSWORD": "capability-test-only-bootstrap",
    "IBEX_AUTH_DB_PASSWORD": "capability-test-only-auth",
}
_WORKER_LOGIN = "ibex_worker"


def _capability_dsn(postgres_dsn: str, role: str) -> str:
    """Return ``postgres_dsn`` with the userinfo replaced by a capability login."""
    parts = urlsplit(postgres_dsn)
    host = parts.hostname or "127.0.0.1"
    port = f":{parts.port}" if parts.port else ""
    password = quote(_CAPABILITY_PASSWORDS["IBEX_WORKER_DB_PASSWORD"], safe="")
    netloc = f"{role}:{password}@{host}{port}"
    return urlunsplit(parts._replace(netloc=netloc))


@pytest.fixture(scope="session")
def capability_worker_dsn(postgres_dsn: str) -> str:
    """Provision and return a DSN that logs in as ``ibex_worker``.

    The capability logins are created by migration 000064 with no password and
    ``CONNECTION LIMIT 0``, so a test that needs a non-superuser login must run
    the provisioning command first. ``migrate provision`` is the Go CLI for the
    same routine the Go integration packages call.
    """
    repo_root = Path(__file__).resolve().parents[4]
    go = shutil.which("go")
    if go is None:
        pytest.fail(
            "go is required to provision the ibex_worker capability login "
            "(migrate provision); install Go or run the Go migration tests first"
        )
    env = dict(os.environ)
    env["POSTGRES_DSN"] = postgres_dsn
    env.update(_CAPABILITY_PASSWORDS)
    try:
        subprocess.run(
            [go, "run", "./infra/migrations/postgres/cmd/migrate", "-command", "provision"],
            cwd=repo_root,
            env=env,
            check=True,
            capture_output=True,
            text=True,
            timeout=300,
        )
    except subprocess.CalledProcessError as exc:  # pragma: no cover - env failure path
        pytest.fail(f"migrate provision failed: {exc.stderr.strip() or exc.stdout.strip()}")
    return _capability_dsn(postgres_dsn, _WORKER_LOGIN)


def _free_tcp_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


@pytest.fixture
def integration_settings(require_redis: str, require_postgres: str) -> Iterator[Settings]:
    get_settings.cache_clear()
    reset_observability_for_tests()
    os.environ["REDIS_URL"] = require_redis
    os.environ["POSTGRES_DSN"] = require_postgres
    os.environ["POSTGRES_TEST_DSN"] = require_postgres
    os.environ["IBEX_WORKER_METRICS_PORT"] = str(_free_tcp_port())
    settings = get_settings()
    yield settings
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
async def truncate_failed_tasks(integration_settings: Settings) -> None:
    if not integration_settings.database_url:
        pytest.skip("database_url not configured")
    _assert_destructive_postgres_opt_in()
    engine = create_engine(integration_settings)
    async with engine.begin() as conn:
        await conn.execute(
            text(  # nosemgrep: python.sqlalchemy.security.audit.avoid-sqlalchemy-text.avoid-sqlalchemy-text
                "TRUNCATE ibex_core.failed_tasks"
            )
        )
    await engine.dispose()
