"""Tests for lifespan startup logic: TEI health wait, geometry check, failure modes."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from unittest.mock import AsyncMock, MagicMock, patch

import numpy as np
import pytest

from app.backends.hosted import HostedAPIBackend
from app.backends.tei import TEIBackend
from app.config import get_settings
from app.errors import BackendUnavailableError, GeometryMismatchError
from app.main import _verify_hosted_geometry, _verify_tei_geometry, _wait_for_tei_health

_DIM = 1024
_MODEL = "BAAI/bge-m3"


@dataclass(frozen=True)
class _TeiProbeSpec:
    health_returns: list[bool] | None = None
    info_return: dict | None = None
    info_side_effect: Exception | None = None
    model_id: str = _MODEL
    dimensions: int = _DIM


def _make_tei_backend(spec: _TeiProbeSpec | None = None) -> TEIBackend:
    probe = spec or _TeiProbeSpec()
    backend = MagicMock(spec=TEIBackend)
    backend.model_id = probe.model_id
    backend.dimensions = probe.dimensions

    if probe.health_returns is not None:
        backend.health = AsyncMock(side_effect=probe.health_returns)
    else:
        backend.health = AsyncMock(return_value=True)

    if probe.info_side_effect is not None:
        backend.info = AsyncMock(side_effect=probe.info_side_effect)
    else:
        payload = probe.info_return if probe.info_return is not None else {"model_id": probe.model_id}
        backend.info = AsyncMock(return_value=payload)

    backend.model_id_from_info = MagicMock(
        side_effect=lambda info: info.get("model_id") if isinstance(info, dict) else None
    )
    probe_vec = np.ones((1, probe.dimensions), dtype=np.float32)
    backend.embed = AsyncMock(return_value=probe_vec)
    return backend


class TestWaitForTeiHealth:
    async def test_returns_immediately_when_healthy(self) -> None:
        backend = _make_tei_backend(_TeiProbeSpec(health_returns=[True]))
        await _wait_for_tei_health(backend, timeout_seconds=5.0)
        assert backend.health.call_count == 1
        timeout_used = backend.health.await_args.kwargs["timeout_seconds"]
        assert timeout_used == pytest.approx(5.0, abs=0.05)

    async def test_retries_until_healthy(self) -> None:
        backend = _make_tei_backend(_TeiProbeSpec(health_returns=[False, False, True]))
        with patch("app.main.asyncio.sleep", new=AsyncMock()):
            await _wait_for_tei_health(backend, timeout_seconds=5.0)
        assert backend.health.call_count == 3

    async def test_raises_after_timeout(self) -> None:
        backend = _make_tei_backend(_TeiProbeSpec(health_returns=[False] * 100))
        with (
            patch("app.main.asyncio.sleep", new=AsyncMock()),
            patch("app.main.time") as mock_time,
        ):
            # Simulate monotonic clock advancing past deadline after 2 polls.
            mock_time.monotonic.side_effect = [0.0, 0.0, 1.0, 10.0, 10.0]
            with pytest.raises(BackendUnavailableError, match="not become healthy"):
                await _wait_for_tei_health(backend, timeout_seconds=5.0)

    async def test_poll_interval_capped_at_remaining_time(self) -> None:
        """When remaining < poll interval, sleep should use remaining, not full interval."""
        backend = _make_tei_backend(_TeiProbeSpec(health_returns=[False, True]))
        sleep_calls: list[float] = []

        async def fake_sleep(delay: float) -> None:
            sleep_calls.append(delay)

        with (
            patch("app.main.asyncio.sleep", side_effect=fake_sleep),
            patch("app.main.time") as mock_time,
        ):
            # _wait_for_tei_health monotonic() call order:
            #   call 1: deadline = monotonic() + timeout  → 0.0 + 5.0 = 5.0
            #   call 2: remaining = 5.0 - monotonic()     → 5.0 - 4.9 = 0.1
            # Then sleep(min(1.0, 0.1)) = sleep(0.1).
            mock_time.monotonic.side_effect = [0.0, 4.9, 4.9, 4.91]
            await _wait_for_tei_health(backend, timeout_seconds=5.0)
        assert sleep_calls[0] == pytest.approx(0.1, abs=0.05)

    async def test_health_call_is_bounded_by_remaining_deadline(self) -> None:
        backend = _make_tei_backend()

        async def bounded_health(*, timeout_seconds: float) -> bool:
            await asyncio.sleep(min(timeout_seconds, 0.01))
            return False

        backend.health = AsyncMock(side_effect=bounded_health)
        with (
            patch("app.main.asyncio.sleep", new=AsyncMock()),
            pytest.raises(BackendUnavailableError, match="not become healthy"),
        ):
            await _wait_for_tei_health(backend, timeout_seconds=0.05)


class TestVerifyTeiGeometry:
    async def test_passes_when_model_id_matches(self) -> None:
        backend = _make_tei_backend(_TeiProbeSpec(info_return={"model_id": _MODEL}))
        await _verify_tei_geometry(backend)  # must not raise

    async def test_raises_on_model_id_mismatch(self) -> None:
        backend = _make_tei_backend(
            _TeiProbeSpec(model_id=_MODEL, info_return={"model_id": "wrong-model"})
        )
        backend.model_id_from_info = MagicMock(return_value="wrong-model")
        with pytest.raises(GeometryMismatchError, match="mismatch"):
            await _verify_tei_geometry(backend)

    async def test_raises_when_info_fetch_fails(self) -> None:
        backend = _make_tei_backend(
            _TeiProbeSpec(info_side_effect=BackendUnavailableError("no /info endpoint"))
        )
        with pytest.raises(BackendUnavailableError, match="no /info endpoint"):
            await _verify_tei_geometry(backend)

    async def test_raises_when_model_id_absent_from_info(self) -> None:
        backend = _make_tei_backend(_TeiProbeSpec(info_return={"other_field": "irrelevant"}))
        backend.model_id_from_info = MagicMock(return_value=None)
        with pytest.raises(BackendUnavailableError, match="did not return model_id"):
            await _verify_tei_geometry(backend)

    async def test_passes_when_model_id_present_and_matches(self) -> None:
        backend = _make_tei_backend(_TeiProbeSpec(info_return={"model_id": _MODEL}))
        backend.model_id_from_info = MagicMock(return_value=_MODEL)
        await _verify_tei_geometry(backend)
        backend.embed.assert_awaited_once()

    async def test_raises_when_info_reports_wrong_dimensions(self) -> None:
        backend = _make_tei_backend(
            _TeiProbeSpec(info_return={"model_id": _MODEL, "hidden_size": 768})
        )
        with pytest.raises(GeometryMismatchError, match="dimensions mismatch"):
            await _verify_tei_geometry(backend)

    async def test_raises_when_probe_dimensions_mismatch(self) -> None:
        backend = _make_tei_backend(_TeiProbeSpec(info_return={"model_id": _MODEL}))
        backend.embed = AsyncMock(return_value=np.ones((1, 768), dtype=np.float32))
        with pytest.raises(GeometryMismatchError, match="dimensions mismatch"):
            await _verify_tei_geometry(backend)


class TestVerifyHostedGeometry:
    async def test_passes_when_probe_matches(self) -> None:
        backend = MagicMock(spec=HostedAPIBackend)
        backend.provider = "openai"
        backend.model_id = "text-embedding-3-large"
        backend.dimensions = 8
        backend.embed = AsyncMock(return_value=np.ones((1, 8), dtype=np.float32))
        await _verify_hosted_geometry(backend)
        backend.embed.assert_awaited_once()

    async def test_raises_on_dim_mismatch(self) -> None:
        backend = MagicMock(spec=HostedAPIBackend)
        backend.provider = "openai"
        backend.model_id = "text-embedding-3-large"
        backend.dimensions = 3072
        backend.embed = AsyncMock(return_value=np.ones((1, 8), dtype=np.float32))
        with pytest.raises(GeometryMismatchError, match="hosted dimensions mismatch"):
            await _verify_hosted_geometry(backend)


class TestLifespanShutdown:
    def test_tei_client_closed_on_shutdown(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Lifespan shutdown must call aclose() on TEI backend."""
        from fastapi.testclient import TestClient

        from app.main import app

        get_settings.cache_clear()
        monkeypatch.setenv("IBEX_EMBEDDING_PROFILE", "gpu")
        monkeypatch.setenv("IBEX_EMBEDDING_TEI_BASE_URL", "http://tei-fake:8080")
        monkeypatch.setenv("IBEX_EMBEDDING_TEI_ALLOW_INSECURE", "true")
        monkeypatch.setenv("IBEX_EMBEDDING_API_TOKEN", "service-token")

        aclose_called = []

        async def fake_aclose():
            aclose_called.append(True)

        with (
            patch("app.main.build_backend") as mock_build,
            patch("app.main._wait_for_tei_health", new=AsyncMock()),
            patch("app.main._verify_tei_geometry", new=AsyncMock()),
            patch("app.main.validate_geometry"),
        ):
            fake_backend = MagicMock(spec=TEIBackend)
            fake_backend.model_id = "BAAI/bge-m3"
            fake_backend.dimensions = 1024
            fake_backend.name = "tei"
            fake_backend.profile = "gpu"
            fake_backend.aclose = AsyncMock(side_effect=fake_aclose)
            mock_build.return_value = fake_backend

            with TestClient(app):
                pass  # context exit triggers lifespan shutdown

        assert aclose_called, "TEI backend aclose() was not called on lifespan shutdown"
        get_settings.cache_clear()

    def test_hosted_client_closed_on_shutdown(self, monkeypatch: pytest.MonkeyPatch) -> None:
        from fastapi.testclient import TestClient

        from app.main import app

        get_settings.cache_clear()
        monkeypatch.setenv("IBEX_EMBEDDING_PROFILE", "hosted")
        monkeypatch.setenv("IBEX_EMBEDDING_HOSTED_API_KEY", "sk-test")
        monkeypatch.setenv("IBEX_EMBEDDING_API_TOKEN", "service-token")

        aclose_called: list[bool] = []

        async def fake_aclose() -> None:
            aclose_called.append(True)

        with (
            patch("app.main.build_backend") as mock_build,
            patch("app.main._verify_hosted_geometry", new=AsyncMock()),
            patch("app.main.validate_geometry"),
        ):
            fake_backend = MagicMock(spec=HostedAPIBackend)
            fake_backend.model_id = "text-embedding-3-large"
            fake_backend.dimensions = 3072
            fake_backend.name = "openai"
            fake_backend.profile = "hosted"
            fake_backend.provider = "openai"
            fake_backend.aclose = AsyncMock(side_effect=fake_aclose)
            mock_build.return_value = fake_backend

            with TestClient(app):
                pass

        assert aclose_called, "hosted backend aclose() was not called on lifespan shutdown"
        get_settings.cache_clear()


class TestLifespanStartupPaths:
    """Verify lifespan startup error handling via TestClient."""

    def _ready(self, monkeypatch: pytest.MonkeyPatch, env: dict[str, str | None]):
        from fastapi.testclient import TestClient

        from app.main import app

        get_settings.cache_clear()
        for key, value in env.items():
            if value is None:
                monkeypatch.delenv(key, raising=False)
            else:
                monkeypatch.setenv(key, value)
        with TestClient(app) as tc:
            resp = tc.get("/ready")
        get_settings.cache_clear()
        return resp

    @pytest.mark.parametrize(
        ("env", "status", "error_code"),
        [
            (
                {
                    "IBEX_EMBEDDING_PROFILE": "gpu",
                    "IBEX_EMBEDDING_TEI_BASE_URL": None,
                    "IBEX_EMBEDDING_API_TOKEN": "service-token",
                },
                503,
                "service_not_ready",
            ),
            (
                {
                    "IBEX_EMBEDDING_PROFILE": "cpu",
                    "IBEX_EMBEDDING_API_TOKEN": "service-token",
                },
                200,
                None,
            ),
            (
                {
                    "IBEX_EMBEDDING_PROFILE": "cpu",
                    "IBEX_EMBEDDING_DIM": "0",
                    "IBEX_EMBEDDING_API_TOKEN": "service-token",
                },
                503,
                None,
            ),
            (
                {
                    "IBEX_EMBEDDING_PROFILE": "cpu",
                    "IBEX_EMBEDDING_API_TOKEN": None,
                },
                503,
                "service_not_ready",
            ),
            (
                {
                    "IBEX_EMBEDDING_PROFILE": "hosted",
                    "IBEX_EMBEDDING_HOSTED_API_KEY": None,
                    "OPENAI_EMBEDDING_API_KEY": None,
                    "IBEX_EMBEDDING_API_TOKEN": "service-token",
                },
                503,
                "service_not_ready",
            ),
        ],
    )
    def test_ready_status_for_startup_env(
        self,
        monkeypatch: pytest.MonkeyPatch,
        env: dict[str, str | None],
        status: int,
        error_code: str | None,
    ) -> None:
        resp = self._ready(monkeypatch, env)
        assert resp.status_code == status
        if error_code is not None:
            assert resp.json()["error"]["code"] == error_code
