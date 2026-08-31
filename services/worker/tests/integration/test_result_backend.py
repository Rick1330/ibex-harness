"""Integration tests — Celery result backend TTL and ignore_result defaults."""

from __future__ import annotations

import pytest
import redis as redis_sync
from celery import Celery

from app.config import Settings
from app.task_names import TASK_EXTRACTION_NOOP, TASK_RESULT_PROBE
from tests.integration.task_wait import (
    wait_for_task_success,
    wait_for_task_total,
    worker_task_total,
)

pytestmark = pytest.mark.integration


def _result_keys(client: redis_sync.Redis) -> list[str]:
    return [key.decode() if isinstance(key, bytes) else str(key) for key in client.scan_iter("celery-task-meta-*")]


def test_ignore_result_default(
    celery_app: Celery,
    worker: object,
    integration_settings: Settings,
) -> None:
    assert celery_app.conf.task_ignore_result is True
    baseline = worker_task_total(celery_app, TASK_EXTRACTION_NOOP)
    # send_task defaults ignore_result=False; apply the app-level policy explicitly.
    celery_app.send_task(
        TASK_EXTRACTION_NOOP,
        queue="extraction",
        ignore_result=celery_app.conf.task_ignore_result,
    )
    wait_for_task_total(celery_app, TASK_EXTRACTION_NOOP, baseline + 1)
    client = redis_sync.Redis.from_url(integration_settings.resolved_result_backend)
    try:
        assert _result_keys(client) == []
    finally:
        client.close()


def test_result_ttl_when_enabled(
    celery_app: Celery,
    worker: object,
    integration_settings: Settings,
) -> None:
    async_result = celery_app.send_task(TASK_RESULT_PROBE, queue="maintenance", ignore_result=False)
    wait_for_task_success(async_result)
    payload = async_result.get(timeout=1)
    assert payload == {"status": "probe", "queue": "maintenance"}
    client = redis_sync.Redis.from_url(integration_settings.resolved_result_backend)
    try:
        keys = _result_keys(client)
        assert keys, "expected result key when ignore_result=False"
        ttl = client.ttl(keys[0])
        assert 0 < ttl <= integration_settings.result_expires_seconds
    finally:
        client.close()
