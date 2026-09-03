"""Unit tests for worker Settings."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from app.config import Settings, redis_url_with_db


def test_redis_url_with_db_replaces_path() -> None:
    assert redis_url_with_db("redis://localhost:6379/0", 1) == "redis://localhost:6379/1"


def test_redis_url_with_db_unix_socket() -> None:
    url = redis_url_with_db("unix:///var/run/redis.sock", 3)
    assert url.startswith("redis+socket:///var/run/redis.sock")
    assert "virtual_host=3" in url


def test_redis_url_with_db_rejects_invalid_scheme() -> None:
    with pytest.raises(ValueError, match="unsupported Redis URL scheme"):
        redis_url_with_db("http://localhost:6379/0", 1)


def test_config_broker_url_from_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("IBEX_WORKER_BROKER_URL", "redis://broker:6379/9")
    monkeypatch.setenv("REDIS_URL", "redis://ignored:6379/0")
    settings = Settings()
    assert settings.resolved_broker_url == "redis://broker:6379/9"


def test_config_derives_queue_db_index(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("IBEX_WORKER_BROKER_URL", raising=False)
    monkeypatch.delenv("IBEX_WORKER_RESULT_BACKEND", raising=False)
    monkeypatch.setenv("REDIS_URL", "redis://localhost:6380/0")
    monkeypatch.setenv("REDIS_DB_QUEUE", "1")
    monkeypatch.setenv("REDIS_DB_RESULTS", "3")
    settings = Settings()
    assert settings.resolved_broker_url == "redis://localhost:6380/1"
    assert settings.resolved_result_backend == "redis://localhost:6380/3"


def test_config_extraction_redis_url_fallback(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("IBEX_WORKER_BROKER_URL", raising=False)
    monkeypatch.delenv("REDIS_URL", raising=False)
    monkeypatch.setenv("IBEX_EXTRACTION_REDIS_URL", "redis://extract:6379/0")
    monkeypatch.setenv("REDIS_DB_QUEUE", "1")
    settings = Settings()
    assert settings.resolved_broker_url == "redis://extract:6379/1"


def test_config_prod_requires_broker(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("IBEX_ENV", "production")
    monkeypatch.delenv("IBEX_WORKER_BROKER_URL", raising=False)
    monkeypatch.delenv("REDIS_URL", raising=False)
    monkeypatch.delenv("IBEX_EXTRACTION_REDIS_URL", raising=False)
    monkeypatch.delenv("IBEX_WORKER_REDIS_URL", raising=False)
    with pytest.raises(ValidationError, match="IBEX_WORKER_BROKER_URL or REDIS_URL"):
        Settings(_env_file=None)


def test_config_prod_allows_worker_redis_url(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("IBEX_ENV", "production")
    monkeypatch.delenv("IBEX_WORKER_BROKER_URL", raising=False)
    monkeypatch.delenv("REDIS_URL", raising=False)
    monkeypatch.delenv("IBEX_EXTRACTION_REDIS_URL", raising=False)
    monkeypatch.setenv("IBEX_WORKER_REDIS_URL", "redis://prod-redis:6379/0")
    settings = Settings(_env_file=None)
    assert settings.resolved_broker_url == "redis://prod-redis:6379/1"


def test_config_empty_broker_url_uses_derived(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("IBEX_WORKER_BROKER_URL", "   ")
    monkeypatch.setenv("REDIS_URL", "redis://localhost:6379/0")
    monkeypatch.setenv("REDIS_DB_QUEUE", "1")
    settings = Settings()
    assert settings.broker_url is None
    assert settings.resolved_broker_url == "redis://localhost:6379/1"


def test_config_redis_url_none_uses_dev_default() -> None:
    settings = Settings(redis_url=None)  # type: ignore[arg-type]
    assert settings.redis_url == "redis://127.0.0.1:6379/0"


def test_config_empty_redis_url_uses_dev_default(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("REDIS_URL", "  ")
    settings = Settings()
    assert settings.redis_url == "redis://127.0.0.1:6379/0"


def test_config_extraction_provider_aliases(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("EXTRACTION_PROVIDER", "vllm")
    monkeypatch.setenv("IBEX_WORKER_EXTRACTION_BASE_URL", "http://127.0.0.1:8000/v1")
    settings = Settings(_env_file=None)
    assert settings.extraction_provider == "vllm"
    assert settings.extraction_vllm_base_url == "http://127.0.0.1:8000/v1"


def test_config_prod_allows_explicit_broker(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("IBEX_ENV", "production")
    monkeypatch.setenv("IBEX_WORKER_BROKER_URL", "redis://prod:6379/1")
    monkeypatch.setenv("IBEX_WORKER_RESULT_BACKEND", "redis://prod:6379/3")
    settings = Settings()
    assert settings.resolved_broker_url == "redis://prod:6379/1"
