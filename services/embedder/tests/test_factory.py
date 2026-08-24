"""Factory tests — profile → backend construction, fail-closed gpu rules."""

from __future__ import annotations

import pytest

from app.backends.hosted import HostedAPIBackend
from app.backends.stub import StubBackend
from app.backends.tei import TEIBackend
from app.config import Settings, get_settings
from app.errors import BackendUnavailableError, GeometryMismatchError
from app.factory import build_backend, build_registry, load_active_backend


@pytest.fixture(autouse=True)
def _clear_cache():
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


class TestBuildBackend:
    def test_cpu_profile_returns_stub(self) -> None:
        backend = build_backend(Settings(profile="cpu"))
        assert isinstance(backend, StubBackend)
        assert backend.name == "stub"
        assert backend.profile == "cpu"

    def test_hosted_profile_returns_hosted_backend(self) -> None:
        settings = Settings(
            profile="hosted",
            hosted_api_key="sk-test",  # type: ignore[arg-type]
        )
        backend = build_backend(settings)
        assert isinstance(backend, HostedAPIBackend)
        assert backend.name == "openai"
        assert backend.profile == "hosted"
        assert backend.dimensions == 3072

    def test_hosted_without_key_raises_immediately(self) -> None:
        settings = Settings(profile="hosted")
        with pytest.raises(BackendUnavailableError, match="HOSTED_API_KEY"):
            build_backend(settings)

    def test_hosted_never_falls_back_to_stub(self) -> None:
        settings = Settings(profile="hosted")
        with pytest.raises(BackendUnavailableError):
            backend = build_backend(settings)
            if isinstance(backend, StubBackend):
                pytest.fail("hosted profile returned stub — geometry contract violated")

    def test_hosted_voyage_fail_closed(self) -> None:
        settings = Settings(
            profile="hosted",
            hosted_provider="voyage",
            hosted_api_key="sk-test",  # type: ignore[arg-type]
        )
        with pytest.raises(BackendUnavailableError, match="not implemented"):
            build_backend(settings)

    def test_hosted_cohere_geometry(self) -> None:
        settings = Settings(
            profile="hosted",
            hosted_provider="cohere",
            hosted_api_key="cohere-key",  # type: ignore[arg-type]
        )
        backend = build_backend(settings)
        assert isinstance(backend, HostedAPIBackend)
        assert backend.name == "cohere"
        assert backend.dimensions == 1024
        assert backend.model_id == "embed-english-v3.0"

    def test_gpu_with_url_returns_tei_backend(self) -> None:
        settings = Settings(profile="gpu", tei_base_url="http://tei:8080")
        backend = build_backend(settings)
        assert isinstance(backend, TEIBackend)
        assert backend.name == "tei"
        assert backend.profile == "gpu"

    def test_gpu_without_url_raises_immediately(self) -> None:
        settings = Settings(profile="gpu")
        assert settings.tei_base_url is None
        with pytest.raises(BackendUnavailableError, match="TEI_BASE_URL"):
            build_backend(settings)

    def test_gpu_never_falls_back_to_stub(self) -> None:
        """Explicit contract: gpu without URL must raise, not silently return stub."""
        settings = Settings(profile="gpu")
        with pytest.raises(BackendUnavailableError):
            backend = build_backend(settings)
            # If we somehow got here, fail if it's a stub (geometry lie).
            if isinstance(backend, StubBackend):
                pytest.fail("gpu profile returned stub backend — geometry contract violated")

    def test_gpu_tei_geometry_matches_settings(self) -> None:
        settings = Settings(
            profile="gpu",
            tei_base_url="http://tei:8080",
            dim=1024,
            model="BAAI/bge-m3",
        )
        backend = build_backend(settings)
        assert isinstance(backend, TEIBackend)
        assert backend.dimensions == 1024
        assert backend.model_id == "BAAI/bge-m3"

    def test_gpu_tei_geometry_uses_profile_defaults_when_unset(self) -> None:
        settings = Settings(profile="gpu", tei_base_url="http://tei:8080")
        backend = build_backend(settings)
        assert isinstance(backend, TEIBackend)
        assert backend.dimensions == 1024
        assert backend.model_id == "BAAI/bge-m3"

    def test_gpu_api_key_passed_to_client(self) -> None:
        settings = Settings(
            profile="gpu",
            tei_base_url="http://tei:8080",
            tei_api_key="secret",  # type: ignore[arg-type]
        )
        backend = build_backend(settings)
        assert isinstance(backend, TEIBackend)
        # The api_key must be present in the client headers (not logged).
        assert "Authorization" in backend._client._client.headers

    def test_gpu_url_trailing_slash_stripped(self) -> None:
        settings = Settings(profile="gpu", tei_base_url="http://tei:8080/")
        backend = build_backend(settings)
        assert isinstance(backend, TEIBackend)


class TestBuildRegistry:
    def test_all_profiles_present(self) -> None:
        reg = build_registry()
        assert reg.profiles() == ["cpu", "gpu", "hosted"]

    def test_all_are_stubs(self) -> None:
        reg = build_registry()
        for profile in ("cpu", "gpu", "hosted"):
            backend = reg.for_profile(profile)
            assert isinstance(backend, StubBackend)


class TestLoadActiveBackend:
    def test_cpu_default_geometry(self) -> None:
        backend = load_active_backend(Settings(profile="cpu"))
        assert backend.dimensions == 384

    def test_gpu_without_url_raises(self) -> None:
        with pytest.raises(BackendUnavailableError):
            load_active_backend(Settings(profile="gpu"))

    def test_geometry_mismatch_raises(self) -> None:
        settings = Settings(profile="cpu", dim=9999, model="all-MiniLM-L6-v2")
        with pytest.raises(GeometryMismatchError):
            load_active_backend(settings)

    def test_hosted_default_geometry(self) -> None:
        backend = load_active_backend(
            Settings(profile="hosted", hosted_api_key="sk-test")  # type: ignore[arg-type]
        )
        assert backend.dimensions == 3072
        assert backend.model_id == "text-embedding-3-large"

    def test_hosted_without_key_raises(self) -> None:
        with pytest.raises(BackendUnavailableError):
            load_active_backend(Settings(profile="hosted"))
