"""Integration tests — Celery beat triggers maintenance noop sweep."""

from __future__ import annotations

import subprocess
import sys
import time
from pathlib import Path

import pytest

from app.celery_app import create_celery_app
from app.task_names import TASK_MAINTENANCE_NOOP_SWEEP

pytestmark = pytest.mark.integration

_WORKER_DIR = Path(__file__).resolve().parents[2]


def test_beat_triggers_maintenance_noop(integration_settings) -> None:
    monitor_app = create_celery_app(integration_settings)
    env = {
        **dict(__import__("os").environ),
        "REDIS_URL": integration_settings.redis_url,
        "REDIS_DB_QUEUE": str(integration_settings.redis_db_queue),
        "REDIS_DB_RESULTS": str(integration_settings.redis_db_results),
        "IBEX_WORKER_MAINTENANCE_BEAT_SECONDS": "1",
    }
    worker_cmd = [
        sys.executable,
        "-m",
        "celery",
        "-A",
        "app.celery_app:celery_app",
        "worker",
        "-Q",
        "maintenance",
        "--pool=solo",
        "--concurrency=1",
        "--loglevel=warning",
    ]
    beat_cmd = [
        sys.executable,
        "-m",
        "celery",
        "-A",
        "app.celery_app:celery_app",
        "beat",
        "--loglevel=warning",
    ]
    worker_proc = subprocess.Popen(
        worker_cmd,
        cwd=_WORKER_DIR,
        env=env,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    beat_proc = subprocess.Popen(
        beat_cmd,
        cwd=_WORKER_DIR,
        env=env,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    try:
        deadline = time.monotonic() + 20.0
        observed = False
        while time.monotonic() < deadline:
            replies = monitor_app.control.ping(timeout=1.0)
            if not replies:
                time.sleep(0.5)
                continue
            stats = monitor_app.control.inspect(timeout=2.0).stats()
            if stats:
                for node in stats.values():
                    total = node.get("total", {})
                    if total.get(TASK_MAINTENANCE_NOOP_SWEEP, 0) >= 1:
                        observed = True
                        break
            if observed:
                break
            time.sleep(0.5)
        assert observed, "beat did not trigger maintenance noop within deadline"
    finally:
        beat_proc.terminate()
        worker_proc.terminate()
        beat_proc.wait(timeout=5)
        worker_proc.wait(timeout=5)
