"""Environment-backed memory service configuration (IBEX_MEMORY_* + ranking/HNSW knobs)."""

from __future__ import annotations

from functools import lru_cache

from pydantic import AliasChoices, Field, SecretStr, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

_WEIGHT_EPS = 1e-9


class Settings(BaseSettings):
    """Settings for the memory substrate service (Phase 3 Track B bootstrap).

    Ranking / HNSW knobs use the unprefixed names already reserved in
    ENVIRONMENT_VARIABLES.md §11 (IBEX_HNSW_EF_SEARCH, IBEX_RANK_WEIGHT_*).
    Service-local knobs use IBEX_MEMORY_*.
    """

    model_config = SettingsConfigDict(
        env_prefix="IBEX_MEMORY_",
        case_sensitive=False,
        extra="ignore",
        populate_by_name=True,
    )

    host: str = Field(
        default="127.0.0.1",
        description="Bind host (containers set IBEX_MEMORY_HOST=0.0.0.0 explicitly)",
    )
    port: int = Field(default=8005, description="Bind port")

    database_url: str | None = Field(
        default=None,
        description="Async Postgres DSN (postgresql+asyncpg://...); required for VectorStore",
    )

    vector_search_min_similarity: float = Field(
        default=0.70,
        ge=0.0,
        le=1.0,
        description="Default min cosine similarity for vector search",
    )

    hnsw_ef_search: int = Field(
        default=40,
        ge=1,
        validation_alias=AliasChoices("IBEX_HNSW_EF_SEARCH", "IBEX_MEMORY_HNSW_EF_SEARCH"),
        description="Per-transaction HNSW ef_search",
    )

    rank_weight_relevance: float = Field(
        default=0.40,
        ge=0.0,
        le=1.0,
        validation_alias=AliasChoices(
            "IBEX_RANK_WEIGHT_RELEVANCE", "IBEX_MEMORY_RANK_WEIGHT_RELEVANCE"
        ),
    )
    rank_weight_recency: float = Field(
        default=0.25,
        ge=0.0,
        le=1.0,
        validation_alias=AliasChoices(
            "IBEX_RANK_WEIGHT_RECENCY", "IBEX_MEMORY_RANK_WEIGHT_RECENCY"
        ),
    )
    rank_weight_usefulness: float = Field(
        default=0.20,
        ge=0.0,
        le=1.0,
        validation_alias=AliasChoices(
            "IBEX_RANK_WEIGHT_USEFULNESS", "IBEX_MEMORY_RANK_WEIGHT_USEFULNESS"
        ),
    )
    rank_weight_confidence: float = Field(
        default=0.10,
        ge=0.0,
        le=1.0,
        validation_alias=AliasChoices(
            "IBEX_RANK_WEIGHT_CONFIDENCE", "IBEX_MEMORY_RANK_WEIGHT_CONFIDENCE"
        ),
    )
    rank_weight_frequency: float = Field(
        default=0.05,
        ge=0.0,
        le=1.0,
        validation_alias=AliasChoices(
            "IBEX_RANK_WEIGHT_FREQUENCY", "IBEX_MEMORY_RANK_WEIGHT_FREQUENCY"
        ),
    )

    embedding_base_url: str = Field(
        default="http://127.0.0.1:8004",
        description="Base URL of the embedder service",
    )
    embedding_api_token: SecretStr | None = Field(
        default=None,
        validation_alias=AliasChoices(
            "IBEX_EMBEDDING_API_TOKEN", "IBEX_MEMORY_EMBEDDING_API_TOKEN"
        ),
        description="Bearer token for embedder POST /v1/embed",
    )
    embedding_timeout_seconds: float = Field(default=30.0, gt=0)
    embedding_connect_timeout_seconds: float = Field(default=2.0, gt=0)
    embedding_max_retries: int = Field(default=2, ge=0)

    @field_validator("database_url", mode="before")
    @classmethod
    def _empty_dsn_to_none(cls, value: object) -> object:
        if value is None:
            return None
        if isinstance(value, str) and not value.strip():
            return None
        return value

    @model_validator(mode="after")
    def _weights_sum_to_one(self) -> Settings:
        total = (
            self.rank_weight_relevance
            + self.rank_weight_recency
            + self.rank_weight_usefulness
            + self.rank_weight_confidence
            + self.rank_weight_frequency
        )
        if abs(total - 1.0) > _WEIGHT_EPS:
            msg = f"rank weights must sum to 1.0, got {total}"
            raise ValueError(msg)
        return self


@lru_cache
def get_settings() -> Settings:
    return Settings()
