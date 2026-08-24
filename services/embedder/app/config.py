"""Environment-backed service configuration (IBEX_EMBEDDING_*)."""

from __future__ import annotations

from functools import lru_cache

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

from app.limits import MAX_MODEL_ID_LEN
from app.profiles import Profile, default_geometry, valid_profile
from app.registry import BackendRegistry
from app.stub import StubBackend
from app.validate import validate_geometry


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="IBEX_EMBEDDING_",
        case_sensitive=False,
        extra="ignore",
    )

    profile: Profile = Field(default="cpu", description="Deployment profile key")
    dim: int | None = Field(default=None, description="Expected vector dimensionality")
    model: str | None = Field(default=None, description="Expected model identifier")

    @field_validator("profile")
    @classmethod
    def _check_profile(cls, value: str) -> str:
        if not valid_profile(value):
            raise ValueError(f"unknown embedding profile: {value!r}")
        return value.strip()

    @field_validator("dim")
    @classmethod
    def _check_dim(cls, value: int | None) -> int | None:
        if value is not None and value < 1:
            raise ValueError("embedding dim must be positive")
        return value

    @field_validator("model")
    @classmethod
    def _check_model(cls, value: str | None) -> str | None:
        if value is None:
            return None
        trimmed = value.strip()
        if not trimmed:
            raise ValueError("embedding model must be non-empty when set")
        if len(trimmed) > MAX_MODEL_ID_LEN:
            raise ValueError(
                f"embedding model exceeds max length {MAX_MODEL_ID_LEN} characters"
            )
        return trimmed

    def resolved_geometry(self) -> tuple[int, str]:
        defaults = default_geometry(self.profile)
        dim = self.dim if self.dim is not None else defaults.dimensions
        model = self.model if self.model is not None else defaults.model_id
        return dim, model


@lru_cache
def get_settings() -> Settings:
    return Settings()


def build_registry() -> BackendRegistry:
    """Construct stub backends for all profiles (M1). Real backends replace entries in M2/M3."""
    backends: dict[str, StubBackend] = {}
    for profile in ("cpu", "gpu", "hosted"):
        backends[profile] = StubBackend.for_profile(profile)  # type: ignore[arg-type]
    return BackendRegistry(backends)


def load_active_backend(settings: Settings | None = None) -> StubBackend:
    """Select and validate the deployment backend from settings."""
    cfg = settings or get_settings()
    registry = build_registry()
    backend = registry.for_profile(cfg.profile)
    want_dim, want_model = cfg.resolved_geometry()
    validate_geometry(backend, want_dim, want_model)
    return backend  # type: ignore[return-value]
