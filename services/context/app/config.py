"""Context assembly settings (milestone 3.5.C.2)."""

from __future__ import annotations

import math

from pydantic import AliasChoices, Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


def _parse_timeout_ms(value: object) -> float:
    """Accept plain milliseconds or Go-style duration suffixes used in docs (``45ms``)."""
    if isinstance(value, bool):
        raise TypeError("timeout must be a number")
    if isinstance(value, (int, float)):
        parsed = float(value)
    else:
        parsed = _parse_timeout_text(str(value))
    if not math.isfinite(parsed):
        raise ValueError("timeout must be finite")
    return parsed


def _parse_timeout_text(text: str) -> float:
    normalized = text.strip().lower()
    if normalized.endswith("ms"):
        return float(normalized[:-2].strip())
    if normalized.endswith("s"):
        return float(normalized[:-1].strip()) * 1000.0
    return float(normalized)


class ContextSettings(BaseSettings):
    """Env-backed knobs for parallel retrieval.

    ``IBEX_CONTEXT_TIMEOUT`` is the outer wall-clock budget (default 45ms per
    ENVIRONMENT_VARIABLES.md). Per-branch timeouts are tighter for cheap paths
    (directive Redis GET, hot HTTP) and equal to the outer budget for cold
    search, which embeds server-side and often exceeds 45ms — fail-open.
    """

    model_config = SettingsConfigDict(extra="ignore")

    timeout_ms: float = Field(
        default=45.0,
        gt=0,
        allow_inf_nan=False,
        validation_alias=AliasChoices("IBEX_CONTEXT_TIMEOUT", "IBEX_CONTEXT_TIMEOUT_MS"),
    )
    directive_timeout_ms: float = Field(
        default=5.0,
        gt=0,
        allow_inf_nan=False,
        validation_alias="IBEX_CONTEXT_DIRECTIVE_TIMEOUT_MS",
    )
    hot_timeout_ms: float = Field(
        default=15.0,
        gt=0,
        allow_inf_nan=False,
        validation_alias="IBEX_CONTEXT_HOT_TIMEOUT_MS",
    )
    cold_timeout_ms: float = Field(
        default=45.0,
        gt=0,
        allow_inf_nan=False,
        validation_alias="IBEX_CONTEXT_COLD_TIMEOUT_MS",
    )
    memory_base_url: str = Field(
        default="",
        validation_alias=AliasChoices(
            "IBEX_CONTEXT_MEMORY_BASE_URL",
            "MEMORY_BASE_URL",
        ),
    )
    memory_api_token: str = Field(
        default="",
        validation_alias=AliasChoices(
            "IBEX_CONTEXT_MEMORY_API_TOKEN",
            "MEMORY_API_TOKEN",
        ),
    )
    redis_url: str = Field(
        default="",
        validation_alias=AliasChoices("IBEX_CONTEXT_REDIS_URL", "REDIS_URL"),
    )

    @field_validator(
        "timeout_ms",
        "directive_timeout_ms",
        "hot_timeout_ms",
        "cold_timeout_ms",
        mode="before",
    )
    @classmethod
    def _coerce_timeout_ms(cls, value: object) -> float:
        return _parse_timeout_ms(value)
