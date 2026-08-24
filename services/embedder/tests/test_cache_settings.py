"""Cache settings, factory wrap, HTTP org_id, and /metrics."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import numpy as np
import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError

from app.backends.stub import StubBackend
from app.cache.backend import CachingEmbeddingBackend
from app.config import Settings, get_settings
from app.factory import build_backend, unwrap_backend
from app.main import app
from app.state import AppState

_ORG = "11111111-1111-1111-1111-111111111111"
_TOKEN = "service-token"


@pytest.fixture(autouse=True)
def _clear_env(monkeypatch: pytest.MonkeyPatch):
    for key in (
        "IBEX_EMBEDDING_CACHE_ENABLED",
        "IBEX_EMBEDDING_CACHE_TTL_SECONDS",
        "IBEX_EMBEDDING_CACHE_REDIS_URL",
        "IBEX_EMBEDDING_CACHE_REDIS_TIMEOUT_SECONDS",
        "REDIS_URL",
        "IBEX_EMBEDDING_API_TOKEN",
        "IBEX_EMBEDDING_PROFILE",
    ):
        monkeypatch.delenv(key, raising=False)
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


class TestCacheSettings:
    def test_defaults_cache_disabled(self) -> None:
        settings = Settings()
        assert settings.cache_enabled is False
        assert settings.cache_ttl_seconds == 86400
        assert settings.resolved_cache_redis_url() is None

    def test_redis_url_fallback(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("REDIS_URL", "redis://127.0.0.1:6379/0")
        settings = Settings()
        assert settings.resolved_cache_redis_url() == "redis://127.0.0.1:6379/0"

    def test_cache_redis_url_overrides_redis_url(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("REDIS_URL", "redis://127.0.0.1:6379/0")
        monkeypatch.setenv(
            "IBEX_EMBEDDING_CACHE_REDIS_URL", "redis://127.0.0.1:6379/2"
        )
        settings = Settings()
        assert settings.resolved_cache_redis_url() == "redis://127.0.0.1:6379/2"

    def test_ttl_rejects_zero(self) -> None:
        with pytest.raises(ValidationError):
            Settings(cache_ttl_seconds=0)

    def test_redis_timeout_rejects_non_finite(self) -> None:
        with pytest.raises(ValidationError):
            Settings(cache_redis_timeout_seconds=float("nan"))
        with pytest.raises(ValidationError):
            Settings(cache_redis_timeout_seconds=float("inf"))

    def test_enabled_without_url_fails_runtime_security(self) -> None:
        settings = Settings(
            cache_enabled=True,
            api_token="token",  # type: ignore[arg-type]
        )
        with pytest.raises(ValueError, match="REDIS_URL"):
            settings.validate_runtime_security()

    def test_rejects_bad_redis_scheme(self) -> None:
        with pytest.raises(ValidationError):
            Settings(cache_redis_url="http://localhost:6379/0")

    def test_rejects_empty_and_hostless_redis_url(self) -> None:
        with pytest.raises(ValidationError):
            Settings(cache_redis_url="   ")
        with pytest.raises(ValidationError):
            Settings(cache_redis_url="redis:///0")


class TestFactoryCacheWrap:
    def test_cache_disabled_returns_stub(self) -> None:
        backend = build_backend(Settings(profile="cpu", cache_enabled=False))
        assert isinstance(backend, StubBackend)

    def test_cache_enabled_wraps_stub(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("REDIS_URL", "redis://127.0.0.1:6379/0")
        settings = Settings(profile="cpu", cache_enabled=True)
        backend = build_backend(settings)
        assert isinstance(backend, CachingEmbeddingBackend)
        assert isinstance(unwrap_backend(backend), StubBackend)
        assert backend.name == "stub"


class TestEmbedOrgIdRequired:
    def test_missing_org_id_returns_400(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("IBEX_EMBEDDING_PROFILE", "cpu")
        monkeypatch.setenv("IBEX_EMBEDDING_API_TOKEN", _TOKEN)
        state = AppState()
        state.ready = True
        backend = MagicMock()
        backend.embed = AsyncMock(return_value=np.ones((1, 8), dtype=np.float32))
        backend.model_id = "m"
        backend.dimensions = 8
        backend.name = "stub"
        state.backend = backend
        with TestClient(app) as tc:
            tc.app.state.embedder = state
            resp = tc.post(
                "/v1/embed",
                json={"texts": ["hello"]},
                headers={"Authorization": f"Bearer {_TOKEN}"},
            )
        assert resp.status_code == 400
        assert resp.json()["error"]["code"] == "invalid_request"

    def test_invalid_org_id_returns_400(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("IBEX_EMBEDDING_PROFILE", "cpu")
        monkeypatch.setenv("IBEX_EMBEDDING_API_TOKEN", _TOKEN)
        state = AppState()
        state.ready = True
        state.backend = MagicMock()
        with TestClient(app) as tc:
            tc.app.state.embedder = state
            resp = tc.post(
                "/v1/embed",
                json={"texts": ["hello"], "org_id": "not-a-uuid"},
                headers={"Authorization": f"Bearer {_TOKEN}"},
            )
        assert resp.status_code == 400

    def test_metrics_endpoint_requires_bearer(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("IBEX_EMBEDDING_PROFILE", "cpu")
        monkeypatch.setenv("IBEX_EMBEDDING_API_TOKEN", _TOKEN)
        with TestClient(app) as tc:
            unauth = tc.get("/metrics")
            assert unauth.status_code == 401
            auth = tc.get("/metrics", headers={"Authorization": f"Bearer {_TOKEN}"})
        assert auth.status_code == 200
        assert "text/plain" in auth.headers["content-type"]


class TestCacheStartupFailClosed:
    def test_cache_enabled_unreachable_redis_not_ready(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("IBEX_EMBEDDING_PROFILE", "cpu")
        monkeypatch.setenv("IBEX_EMBEDDING_API_TOKEN", _TOKEN)
        monkeypatch.setenv("IBEX_EMBEDDING_CACHE_ENABLED", "true")
        monkeypatch.setenv("REDIS_URL", "redis://127.0.0.1:1/0")
        monkeypatch.setenv("IBEX_EMBEDDING_CACHE_REDIS_TIMEOUT_SECONDS", "0.05")
        get_settings.cache_clear()
        with TestClient(app) as tc:
            ready = tc.get("/ready")
        assert ready.status_code == 503
        assert "cache" in ready.json()["error"]["message"].lower() or (
            ready.json()["error"]["code"] == "service_not_ready"
        )
