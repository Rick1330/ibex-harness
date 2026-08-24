"""Environment-backed service configuration (IBEX_EMBEDDING_*)."""

from __future__ import annotations

from functools import lru_cache
from urllib.parse import urlparse

from pydantic import Field, SecretStr, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

from app.hosted.env import HostedEnvMixin
from app.hosted.providers import resolve_hosted_geometry
from app.limits import MAX_MODEL_ID_LEN
from app.profiles import Profile, default_geometry, valid_profile


class Settings(HostedEnvMixin, BaseSettings):
    """All settings are read from IBEX_EMBEDDING_* environment variables.

    TEI-specific settings use the IBEX_EMBEDDING_TEI_* sub-namespace.
    Hosted-API settings use IBEX_EMBEDDING_HOSTED_*.
    pydantic-settings maps snake_case field names to UPPER_SNAKE env vars
    under the configured prefix, so `tei_base_url` → IBEX_EMBEDDING_TEI_BASE_URL.
    """

    model_config = SettingsConfigDict(
        env_prefix="IBEX_EMBEDDING_",
        case_sensitive=False,
        extra="ignore",
        populate_by_name=True,
    )

    profile: Profile = Field(default="cpu", description="Deployment profile key")
    dim: int | None = Field(default=None, description="Expected vector dimensionality")
    model: str | None = Field(default=None, description="Expected model identifier")

    # TEI sidecar settings — all IBEX_EMBEDDING_TEI_* via env_prefix + field name.
    tei_base_url: str | None = Field(
        default=None,
        description="Base URL of the TEI sidecar (required when profile=gpu)",
    )
    tei_timeout_seconds: float = Field(
        default=30.0,
        description="Read timeout for TEI /embed requests (seconds)",
    )
    tei_connect_timeout_seconds: float = Field(
        default=2.0,
        description="Connect timeout for TEI requests (seconds)",
    )
    tei_api_key: SecretStr | None = Field(
        default=None,
        description="Optional bearer token for TEI auth — never logged",
    )
    tei_allow_insecure: bool = Field(
        default=False,
        description="Development-only escape hatch to allow cleartext TEI URLs",
    )
    tei_max_retries: int = Field(
        default=2,
        description="Max retry attempts for transient TEI errors (0 = no retries)",
    )
    tei_health_timeout_seconds: float = Field(
        default=30.0,
        description="Total time to wait for TEI /health to pass on startup (seconds)",
    )
    api_token: SecretStr | None = Field(
        default=None,
        description="Internal Bearer token required for POST /v1/embed",
    )

    # ------------------------------------------------------------------ #
    # Validators                                                            #
    # ------------------------------------------------------------------ #

    @field_validator("profile")
    @classmethod
    def _check_profile(cls, value: str) -> str:
        stripped = value.strip()
        if not valid_profile(stripped):
            raise ValueError(f"unknown embedding profile: {value!r}")
        return stripped

    @field_validator("dim")
    @classmethod
    def _check_dim(cls, value: int | None) -> int | None:
        if value is not None and value < 1:
            raise ValueError("embedding dim must be >= 1")
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
                f"embedding model id exceeds maximum length of {MAX_MODEL_ID_LEN} characters"
            )
        return trimmed

    @field_validator("tei_base_url")
    @classmethod
    def _check_tei_base_url(cls, value: str | None) -> str | None:
        if value is None:
            return None
        stripped = value.strip().rstrip("/")
        if not stripped:
            raise ValueError("tei_base_url must be non-empty when set")
        parsed = urlparse(stripped)
        scheme = parsed.scheme.lower()
        if scheme not in {"https", "http"}:
            raise ValueError("tei_base_url scheme must be https (or http with TEI_ALLOW_INSECURE)")
        if not parsed.hostname:
            raise ValueError("tei_base_url must include a hostname")
        return stripped

    @field_validator("api_token")
    @classmethod
    def _check_api_token(cls, value: SecretStr | None) -> SecretStr | None:
        if value is None:
            return None
        if not value.get_secret_value().strip():
            raise ValueError("api_token must be non-empty when set")
        return value

    @field_validator("tei_max_retries", "hosted_max_retries")
    @classmethod
    def _check_max_retries(cls, value: int) -> int:
        if value < 0:
            raise ValueError("max_retries must be >= 0")
        return value

    @field_validator(
        "tei_timeout_seconds",
        "tei_connect_timeout_seconds",
        "tei_health_timeout_seconds",
        "hosted_timeout_seconds",
        "hosted_connect_timeout_seconds",
    )
    @classmethod
    def _check_positive_timeout(cls, value: float) -> float:
        if value <= 0:
            raise ValueError("timeout must be > 0")
        return value

    # ------------------------------------------------------------------ #
    # Derived helpers                                                       #
    # ------------------------------------------------------------------ #

    def resolved_geometry(self) -> tuple[int, str]:
        """Return (dimensions, model_id) using env overrides or profile defaults."""
        if self.profile == "hosted":
            return resolve_hosted_geometry(
                self.hosted_provider,
                model=self.model,
                dim=self.dim,
            )
        defaults = default_geometry(self.profile)
        dim = self.dim if self.dim is not None else defaults.dimensions
        model = self.model if self.model is not None else defaults.model_id
        return dim, model

    def validate_runtime_security(self) -> None:
        """Fail closed on insecure or incomplete runtime security settings."""
        self._require_api_token()
        self._require_secure_tei_transport()
        self._require_hosted_api_key()

    def _require_api_token(self) -> None:
        if self.api_token is None or not self.api_token.get_secret_value().strip():
            raise ValueError("IBEX_EMBEDDING_API_TOKEN is required at startup")

    def _require_hosted_api_key(self) -> None:
        if self.profile != "hosted":
            return
        if self.hosted_api_key is None or not self.hosted_api_key.get_secret_value().strip():
            raise ValueError(
                "IBEX_EMBEDDING_HOSTED_API_KEY is required when profile=hosted"
            )

    def _require_secure_tei_transport(self) -> None:
        if self.tei_base_url is None:
            return
        if urlparse(self.tei_base_url).scheme.lower() != "http":
            return
        if not self.tei_allow_insecure:
            raise ValueError(
                "tei_base_url must use https unless IBEX_EMBEDDING_TEI_ALLOW_INSECURE=true"
            )
        if self.tei_api_key is not None:
            raise ValueError(
                "tei_api_key is forbidden when tei_allow_insecure=true (cleartext HTTP)"
            )


@lru_cache
def get_settings() -> Settings:
    return Settings()
