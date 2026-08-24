"""Hosted-profile settings fields and validators (IBEX_EMBEDDING_HOSTED_*)."""

from __future__ import annotations

import os
from typing import Annotated
from urllib.parse import urlparse

from pydantic import BaseModel, BeforeValidator, Field, SecretStr, field_validator, model_validator

from app.hosted.providers import HostedProvider


def _coerce_hosted_provider(value: object) -> object:
    if isinstance(value, str):
        return value.strip().lower()
    return value


def require_https_host_url(url: str, *, field: str) -> str:
    parsed = urlparse(url)
    if parsed.scheme.lower() != "https":
        raise ValueError(f"{field} must use https")
    if not parsed.hostname:
        raise ValueError(f"{field} must include a hostname")
    if parsed.username is not None or parsed.password is not None:
        raise ValueError(f"{field} must not include userinfo")
    return url


class HostedEnvMixin(BaseModel):
    """Hosted API knobs composed into Settings. Env prefix comes from Settings."""

    hosted_provider: Annotated[
        HostedProvider, BeforeValidator(_coerce_hosted_provider)
    ] = Field(
        default="openai",
        description="Hosted embedding provider: openai | cohere | voyage",
    )
    hosted_api_key: SecretStr | None = Field(
        default=None,
        description=(
            "API key for hosted provider — never logged. "
            "Canonical: IBEX_EMBEDDING_HOSTED_API_KEY; "
            "optional OpenAI-only alias: OPENAI_EMBEDDING_API_KEY"
        ),
    )
    hosted_base_url: str | None = Field(
        default=None,
        description="Override hosted provider base URL (HTTPS required)",
    )
    hosted_timeout_seconds: float = Field(
        default=30.0,
        description="Read timeout for hosted embed requests (seconds)",
    )
    hosted_connect_timeout_seconds: float = Field(
        default=2.0,
        description="Connect timeout for hosted requests (seconds)",
    )
    hosted_max_retries: int = Field(
        default=2,
        description="Max retry attempts for transient hosted errors (0 = no retries)",
    )

    @model_validator(mode="after")
    def _alias_openai_embedding_api_key(self) -> HostedEnvMixin:
        if self.hosted_api_key is not None or self.hosted_provider != "openai":
            return self
        alias = os.environ.get("OPENAI_EMBEDDING_API_KEY", "").strip()
        if alias:
            self.hosted_api_key = SecretStr(alias)
        return self

    @field_validator("hosted_api_key")
    @classmethod
    def _check_hosted_api_key(cls, value: SecretStr | None) -> SecretStr | None:
        if value is None:
            return None
        if not value.get_secret_value().strip():
            raise ValueError("hosted_api_key must be non-empty when set")
        return value

    @field_validator("hosted_base_url")
    @classmethod
    def _check_hosted_base_url(cls, value: str | None) -> str | None:
        if value is None:
            return None
        stripped = value.strip().rstrip("/")
        if not stripped:
            raise ValueError("hosted_base_url must be non-empty when set")
        return require_https_host_url(stripped, field="hosted_base_url")
