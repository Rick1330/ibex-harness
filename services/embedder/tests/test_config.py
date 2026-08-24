"""Configuration validation and backend loading tests."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from app.backends.stub import StubBackend
from app.config import Settings, get_settings
from app.errors import DuplicateProfileError, GeometryMismatchError
from app.factory import build_registry, load_active_backend
from app.limits import MAX_MODEL_ID_LEN
from app.registry import BackendRegistry


@pytest.fixture(autouse=True)
def _clear_settings_cache(monkeypatch: pytest.MonkeyPatch):
    for key in (
        "IBEX_EMBEDDING_PROFILE",
        "IBEX_EMBEDDING_DIM",
        "IBEX_EMBEDDING_MODEL",
        "IBEX_EMBEDDING_TEI_BASE_URL",
        "IBEX_EMBEDDING_TEI_API_KEY",
        "IBEX_EMBEDDING_TEI_ALLOW_INSECURE",
        "IBEX_EMBEDDING_API_TOKEN",
    ):
        monkeypatch.delenv(key, raising=False)
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


# ------------------------------------------------------------------ #
# Profile validation                                                   #
# ------------------------------------------------------------------ #

def test_settings_defaults_cpu() -> None:
    settings = Settings()
    dim, model = settings.resolved_geometry()
    assert settings.profile == "cpu"
    assert dim == 384
    assert model == "all-MiniLM-L6-v2"


def test_settings_rejects_unknown_profile() -> None:
    with pytest.raises(ValidationError):
        Settings(profile="nope")  # type: ignore[arg-type]


def test_settings_rejects_empty_profile() -> None:
    with pytest.raises(ValidationError):
        Settings(profile="")  # type: ignore[arg-type]


# ------------------------------------------------------------------ #
# Dim validation                                                       #
# ------------------------------------------------------------------ #

def test_settings_rejects_zero_dim() -> None:
    with pytest.raises(ValidationError, match="dim must be >= 1"):
        Settings(dim=0)


def test_settings_rejects_negative_dim() -> None:
    with pytest.raises(ValidationError):
        Settings(dim=-1)


def test_settings_accepts_positive_dim() -> None:
    s = Settings(dim=512)
    assert s.dim == 512


# ------------------------------------------------------------------ #
# Model id validation                                                  #
# ------------------------------------------------------------------ #

def test_settings_model_id_at_max_length_accepted() -> None:
    Settings(model="m" * MAX_MODEL_ID_LEN)


def test_settings_model_id_over_max_length_rejected() -> None:
    with pytest.raises(ValidationError, match="maximum length"):
        Settings(model="m" * (MAX_MODEL_ID_LEN + 1))


def test_settings_model_id_whitespace_only_rejected() -> None:
    with pytest.raises(ValidationError, match="non-empty"):
        Settings(model="   ")


def test_settings_model_id_strips_whitespace() -> None:
    s = Settings(model=" BAAI/bge-m3 ")
    assert s.model == "BAAI/bge-m3"


# ------------------------------------------------------------------ #
# TEI URL validation                                                   #
# ------------------------------------------------------------------ #

def test_tei_base_url_strips_trailing_slash() -> None:
    s = Settings(tei_base_url="https://tei:8080/")
    assert s.tei_base_url == "https://tei:8080"


def test_tei_base_url_rejects_non_http() -> None:
    with pytest.raises(ValidationError, match="http"):
        Settings(tei_base_url="grpc://tei:8080")


def test_tei_base_url_rejects_empty() -> None:
    with pytest.raises(ValidationError):
        Settings(tei_base_url="   ")


def test_tei_base_url_accepts_https() -> None:
    s = Settings(tei_base_url="https://tei.internal:9000")
    assert s.tei_base_url == "https://tei.internal:9000"


def test_tei_base_url_rejects_http_by_default() -> None:
    settings = Settings(tei_base_url="http://tei:8080", api_token="service-token")  # type: ignore[arg-type]
    with pytest.raises(ValueError, match="must use https"):
        settings.validate_runtime_security()


def test_tei_base_url_allows_http_in_development_mode() -> None:
    settings = Settings(
        tei_base_url="http://tei:8080/",
        tei_allow_insecure=True,
        api_token="service-token",  # type: ignore[arg-type]
    )
    settings.validate_runtime_security()
    assert settings.tei_base_url == "http://tei:8080"


def test_tei_api_key_rejected_with_insecure_http() -> None:
    settings = Settings(
        tei_base_url="http://tei:8080",
        tei_allow_insecure=True,
        tei_api_key="secret",  # type: ignore[arg-type]
        api_token="service-token",  # type: ignore[arg-type]
    )
    with pytest.raises(ValueError, match="forbidden when tei_allow_insecure=true"):
        settings.validate_runtime_security()


def test_runtime_security_requires_service_api_token() -> None:
    with pytest.raises(ValueError, match="IBEX_EMBEDDING_API_TOKEN"):
        Settings().validate_runtime_security()


# ------------------------------------------------------------------ #
# TEI timeout and retry validation                                     #
# ------------------------------------------------------------------ #

def test_tei_max_retries_rejects_negative() -> None:
    with pytest.raises(ValidationError, match="tei_max_retries"):
        Settings(tei_max_retries=-1)


def test_tei_max_retries_accepts_zero() -> None:
    s = Settings(tei_max_retries=0)
    assert s.tei_max_retries == 0


def test_tei_timeout_rejects_zero() -> None:
    with pytest.raises(ValidationError, match="timeout must be > 0"):
        Settings(tei_timeout_seconds=0.0)


def test_tei_timeout_rejects_negative() -> None:
    with pytest.raises(ValidationError):
        Settings(tei_connect_timeout_seconds=-1.0)


# ------------------------------------------------------------------ #
# Factory helpers                                                      #
# ------------------------------------------------------------------ #

def test_build_registry_has_all_profiles() -> None:
    reg = build_registry()
    assert reg.profiles() == ["cpu", "gpu", "hosted"]


def test_load_active_backend_cpu_defaults() -> None:
    backend = load_active_backend(Settings())
    assert backend.name == "stub"
    assert backend.dimensions == 384


def test_load_active_backend_geometry_mismatch() -> None:
    settings = Settings(profile="cpu", dim=1024, model="all-MiniLM-L6-v2")
    with pytest.raises(GeometryMismatchError):
        load_active_backend(settings)


def test_load_active_backend_gpu_without_url_raises() -> None:
    from app.errors import BackendUnavailableError
    settings = Settings(profile="gpu")
    with pytest.raises(BackendUnavailableError, match="TEI_BASE_URL"):
        load_active_backend(settings)


def test_registry_duplicate_profile() -> None:
    cpu = StubBackend.for_profile("cpu")
    dst: dict[str, StubBackend] = {}
    BackendRegistry._register_one(dst, "cpu", cpu)
    with pytest.raises(DuplicateProfileError):
        BackendRegistry._register_one(dst, "cpu", cpu)
