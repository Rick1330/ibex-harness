"""Integration test fixtures (real Redis broker + result backend)."""

from __future__ import annotations

import os
from collections.abc import Iterator

import pytest
import redis as redis_sync
from celery import Celery
from celery.contrib.testing.worker import start_worker
from redis.exceptions import RedisError

from app.celery_app import create_celery_app
from app.config import Settings, get_settings

_REDIS_BASE = os.environ.get("REDIS_URL", "redis://127.0.0.1:6379/0")
_QUEUE_DB = int(os.environ.get("REDIS_DB_QUEUE", "1"))
_RESULTS_DB = int(os.environ.get("REDIS_DB_RESULTS", "3"))


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


@pytest.fixture
def integration_settings(require_redis: str) -> Settings:
    get_settings.cache_clear()
    return Settings(
        redis_url=require_redis,
        redis_db_queue=_QUEUE_DB,
        redis_db_results=_RESULTS_DB,
        env="development",
    )


@pytest.fixture
def celery_app(integration_settings: Settings) -> Celery:
    return create_celery_app(integration_settings)


@pytest.fixture(autouse=True)
def flush_worker_redis_dbs(integration_settings: Settings) -> Iterator[None]:
    """Flush only broker/result DBs — never DB 0 (shared cache)."""
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
