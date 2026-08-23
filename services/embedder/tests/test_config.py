"""Configuration and backend loading tests."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from app.config import Settings, build_registry, get_settings, load_active_backend
from app.errors import DuplicateProfileError, GeometryMismatchError
from app.registry import BackendRegistry
from app.stub import StubBackend


@pytest.fixture(autouse=True)
def _clear_settings_cache() -> None:
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


def test_settings_defaults_cpu() -> None:
    settings = Settings()
    dim, model = settings.resolved_geometry()
    assert settings.profile == "cpu"
    assert dim == 384
    assert model == "all-MiniLM-L6-v2"


def test_settings_rejects_invalid_profile() -> None:
    with pytest.raises(ValidationError):
        Settings(profile="nope")  # type: ignore[arg-type]


def test_build_registry_has_all_profiles() -> None:
    reg = build_registry()
    assert reg.profiles() == ["cpu", "gpu", "hosted"]


def test_load_active_backend_cpu_defaults() -> None:
    backend = load_active_backend(Settings())
    assert backend.name == "stub"
    assert backend.dimensions == 384


def test_load_active_backend_geometry_mismatch() -> None:
    with pytest.raises(GeometryMismatchError):
        load_active_backend(Settings(profile="cpu", dim=1024, model="all-MiniLM-L6-v2"))


def test_registry_duplicate_profile() -> None:
    cpu = StubBackend.for_profile("cpu")
    dst: dict[str, StubBackend] = {}
    BackendRegistry._register_one(dst, "cpu", cpu)
    with pytest.raises(DuplicateProfileError):
        BackendRegistry._register_one(dst, "cpu", cpu)
