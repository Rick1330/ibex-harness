"""Environment-backed memory service configuration (IBEX_MEMORY_* + ranking/HNSW knobs)."""

from __future__ import annotations

from functools import lru_cache

from pydantic import AliasChoices, Field, SecretStr, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

from app.scoring.composite import RankWeights

_WEIGHT_EPS = 1e-9

# ibex_core.memories.embedding_model is TEXT with memories_embedding_model_len_chk
# (char_length <= 256). The composed identity (`id` or `id@revision`) longer than that
# is refused before the write, not at INSERT time against a live row.
_EMBEDDING_MODEL_MAX_CHARS = 256

# Bundled CNN models in services/memory (uv.lock). Transformers / arbitrary names rejected.
_ALLOWED_PII_SPACY_MODELS: frozenset[str] = frozenset(
    {
        "en_core_web_sm",
        "en_core_web_md",
    }
)


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

    environment: str = Field(
        default="development",
        validation_alias=AliasChoices("IBEX_ENV", "IBEX_MEMORY_ENV"),
        description="Deployment profile; outside development the AuthService CA is required",
    )

    @field_validator("environment", mode="before")
    @classmethod
    def _normalize_environment(cls, value: object) -> str:
        return str(value).strip().lower() or "development"

    otel_endpoint: str = Field(
        default="",
        validation_alias=AliasChoices(
            "IBEX_OTEL_EXPORTER_OTLP_ENDPOINT", "OTEL_EXPORTER_OTLP_ENDPOINT"
        ),
        description="OTLP collector endpoint (e.g. http://127.0.0.1:4318); empty disables export",
    )

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

    # Scoring-time relevance floor (ADR-0068) — distinct from vector_search_min_similarity.
    # Must stay strictly below FTS_COMPOSITE_RELEVANCE (0.5) so FTS hits are not mass-excluded.
    composite_relevance_floor: float = Field(
        default=0.15,
        ge=0.0,
        lt=0.5,
        validation_alias=AliasChoices(
            "IBEX_COMPOSITE_RELEVANCE_FLOOR",
            "IBEX_MEMORY_COMPOSITE_RELEVANCE_FLOOR",
        ),
        description=(
            "Scoring-time floor on the composite relevance component; candidates below "
            "are excluded before composite_score (not the ANN min_similarity cutoff). "
            "Must be < 0.5 (FTS composite relevance sentinel)"
        ),
    )

    hnsw_ef_search: int = Field(
        default=64,
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

    # Stored vector identity. The write path records this on every row it embeds, so
    # ibex_core.memories.embedding_model names the generation that produced the vector
    # instead of a literal. The default preserves the id written before it was
    # configurable.
    embedding_model: str = Field(
        default="bge-m3",
        validation_alias="IBEX_MEMORY_EMBEDDING_MODEL",
        description=(
            "Embedding model id; non-empty, max 256 chars "
            "(ibex_core.memories.embedding_model). The recorded value is this id, or "
            "`id@revision` when IBEX_MEMORY_EMBEDDING_MODEL_REVISION is set; the "
            "composite is what lands in the column"
        ),
    )
    embedding_model_revision: str = Field(
        default="",
        validation_alias="IBEX_MEMORY_EMBEDDING_MODEL_REVISION",
        description=(
            "Optional revision of the embedding model (weights digest, tag, or build), "
            "appended to the model id as `@revision` to form the recorded identity "
            "(`bge-m3@r1`). Empty means this deployment does not distinguish revisions "
            "and the recorded value stays the bare id. A vector cached or indexed under "
            "one revision must never be served as the output of another"
        ),
    )

    # PII stage (m3.C.1 / ADR-0054) — distinct from injection quarantine threshold.
    pii_redact_min_confidence: float = Field(
        default=0.70,
        ge=0.0,
        le=1.0,
        description="Findings at/above this score are redacted; any below → quarantined",
    )
    pii_spacy_model: str = Field(
        default="en_core_web_md",
        description="spaCy CNN model for Presidio NER (trf forbidden — Semgrep)",
    )
    max_content_chars: int = Field(
        default=10_000,
        ge=1,
        description="Reject writes whose content exceeds this length",
    )

    # Dedup stages (m3.C.2 / ADR-0055) — exact hash before embed; near-dup after.
    dedup_exact_enabled: bool = Field(
        default=True,
        description="Enable SHA-256 content-hash exact dedup on the write path",
    )
    near_duplicate_sim_threshold: float = Field(
        default=0.92,
        ge=0.0,
        le=1.0,
        description="Cosine similarity floor for near-duplicate candidates (strict >)",
    )
    near_duplicate_candidate_limit: int = Field(
        default=10,
        ge=1,
        le=100,
        description="Max near-duplicate candidates returned from VectorStore.search",
    )

    # Conflict stage (m3.C.3 / ADR-0056).
    conflict_detection_enabled: bool = Field(
        default=True,
        description="Run temporal conflict detection after near-dup",
    )

    redis_url: str | None = Field(
        default=None,
        validation_alias=AliasChoices("IBEX_MEMORY_REDIS_URL", "REDIS_URL"),
        description="Redis URL for hot cache (optional)",
    )
    redis_timeout_seconds: float = Field(default=0.5, gt=0)

    auth_grpc_addr: str = Field(
        default="127.0.0.1:9091",
        validation_alias=AliasChoices("IBEX_AUTH_GRPC_ADDR", "IBEX_MEMORY_AUTH_GRPC_ADDR"),
        description="Auth service gRPC target for ValidateToken",
    )
    auth_grpc_ca_file: str | None = Field(
        default=None,
        validation_alias="IBEX_AUTH_GRPC_CA_FILE",
        description="CA bundle PEM used to verify AuthService gRPC TLS (ADR-0097 §4); "
        "unset keeps the trust-gated plaintext dial",
    )
    auth_timeout_ms: int = Field(default=50, ge=1)

    memory_cache_ttl_seconds: int = Field(default=3600, ge=60)

    search_fallback_enabled: bool = Field(
        default=True,
        description="Supplement sparse vector hits with GIN full-text search (3.D.1)",
    )
    # Hybrid retrieval (phase 5.A.1 + 5.A.2). Off by default until the gold-set
    # comparison in 5.C.1 reads the change as an improvement; the code path is
    # exercised by unit and integration tests and enabled in the dev stack.
    # ADR-0094 leaves suppression unconditional. Operators need a way to turn it off without a
    # deploy: it can hide a memory a user expects to see, and the multi-mode benchmark compares
    # the two behaviours on the same corpus.
    conflict_suppression_enabled: bool = Field(
        default=True,
        description=(
            "Drop the lower-ranked side of an unresolved conflict from search results. "
            "Disabling it returns both sides. Two side effects: a page no longer shortened by "
            "suppression may not trigger the full-text backfill that the enabled path needs, "
            "and context assembly (which has its own collapse, ADR-0094) is unaffected."
        ),
    )
    search_hybrid_enabled: bool = Field(
        default=False,
        description="Run the full-text channel in parallel with vector search and fuse by RRF",
    )
    search_rrf_k: int = Field(
        default=60,
        ge=1,
        le=1000,
        description="Reciprocal rank fusion constant (Cormack et al. 2009; Elasticsearch default)",
    )
    # Cross-encoder reranking (phase 5.A.3). Off by default: it adds a network hop
    # and a model inference to the read path, and only applies to the hybrid window.
    rerank_enabled: bool = Field(
        default=False,
        description="Rerank the fused hybrid window with a TEI cross-encoder before composite scoring",
    )
    rerank_base_url: str = Field(
        default="http://127.0.0.1:8006",
        description="Base URL of the TEI reranker service (POST /rerank)",
    )
    rerank_api_token: SecretStr | None = Field(
        default=None,
        validation_alias=AliasChoices("IBEX_RERANK_API_TOKEN", "IBEX_MEMORY_RERANK_API_TOKEN"),
        description="Optional bearer token for the reranker",
    )
    rerank_timeout_ms: int = Field(
        default=100,
        ge=1,
        le=5000,
        description=(
            "Wall-clock budget for the whole rerank stage, including every split "
            "request, before degrading to the fused order; defaults to the memory "
            "search p95 target"
        ),
    )
    rerank_connect_timeout_ms: int = Field(
        default=50,
        ge=1,
        le=5000,
        description="Connect timeout for the reranker",
    )
    rerank_max_retries: int = Field(
        default=0,
        ge=0,
        le=3,
        description="Retries inside the rerank budget; 0 keeps the read path inside its deadline",
    )
    rerank_max_candidates: int = Field(
        default=50,
        ge=1,
        le=50,
        description=(
            "Upper bound on candidates sent to the reranker per search; the client "
            "splits the window into requests of rerank_client_batch_size"
        ),
    )
    rerank_client_batch_size: int = Field(
        default=32,
        ge=1,
        le=64,
        description=(
            "Documents per POST /rerank request; must not exceed the TEI server's "
            "--max-client-batch-size (default 32). Larger windows are split."
        ),
    )

    @field_validator("database_url", mode="before")
    @classmethod
    def _empty_dsn_to_none(cls, value: object) -> object:
        if value is None:
            return None
        if isinstance(value, str) and not value.strip():
            return None
        return value

    @field_validator("embedding_model", mode="after")
    @classmethod
    def _validate_embedding_model(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("embedding_model must be non-empty")
        if len(normalized) > _EMBEDDING_MODEL_MAX_CHARS:
            raise ValueError(
                "embedding_model must be at most "
                f"{_EMBEDDING_MODEL_MAX_CHARS} characters "
                "(ibex_core.memories.embedding_model)"
            )
        return normalized

    @field_validator("embedding_model_revision", mode="after")
    @classmethod
    def _validate_embedding_model_revision(cls, value: str) -> str:
        normalized = value.strip()
        if len(normalized) > _EMBEDDING_MODEL_MAX_CHARS:
            raise ValueError(
                f"embedding_model_revision must be at most {_EMBEDDING_MODEL_MAX_CHARS} characters"
            )
        return normalized

    @field_validator("pii_spacy_model", mode="after")
    @classmethod
    def _reject_transformers_spacy_model(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            msg = "pii_spacy_model must be non-empty"
            raise ValueError(msg)
        lower = normalized.lower()
        if "trf" in lower or "transformer" in lower:
            msg = (
                "transformer spaCy models are forbidden in services/memory "
                "(ibex-memory-no-ml-imports / ADR-0054); use en_core_web_md"
            )
            raise ValueError(msg)
        if normalized not in _ALLOWED_PII_SPACY_MODELS:
            allowed = ", ".join(sorted(_ALLOWED_PII_SPACY_MODELS))
            msg = f"unsupported pii_spacy_model {normalized!r}; allowed: {allowed}"
            raise ValueError(msg)
        return normalized

    @model_validator(mode="after")
    def _auth_ca_boundary(self) -> Settings:
        if self.environment == "development":
            return self
        if not (self.auth_grpc_ca_file or "").strip():
            raise ValueError(
                "IBEX_AUTH_GRPC_CA_FILE is required outside development; "
                "plaintext AuthService connections are not allowed"
            )
        return self

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

    def rank_weights(self) -> RankWeights:
        """Configured composite weights for production scoring (F4-029)."""
        return RankWeights(
            relevance=self.rank_weight_relevance,
            recency=self.rank_weight_recency,
            usefulness=self.rank_weight_usefulness,
            confidence=self.rank_weight_confidence,
            frequency=self.rank_weight_frequency,
        )


@lru_cache
def get_settings() -> Settings:
    return Settings()


def resolve_embedding_identity(explicit: str | None = None) -> str:
    """The opaque embedding identity a stored vector is recorded under.

    The identity is the model id, plus ``@<revision>`` when
    ``IBEX_MEMORY_EMBEDDING_MODEL_REVISION`` is non-empty: ``bge-m3``, or
    ``bge-m3@r1`` when revision ``r1`` is configured. ``@`` is the separator and the
    value is opaque: the search fence must be given the same full string, because
    ``ibex_core.memories.embedding_model`` compares byte-identically. With no
    revision configured the identity is exactly the model id, so rows written before
    the revision existed keep matching.

    ``explicit`` supplies the model id when it is a non-blank string (a composition
    root or a test pinning the identity); the revision still comes from configuration.
    Otherwise process configuration decides. Both write-path writers resolve through
    here so the outcome and the after-commit upsert cannot disagree about which
    generation produced the vector.

    Raises:
        ValueError: the composed identity exceeds the 256-character
            ``memories_embedding_model_len_chk`` limit, which would otherwise fail the
            INSERT after the caller was told the write succeeded.
    """
    settings = get_settings()
    model_id = explicit.strip() if explicit is not None else ""
    if not model_id:
        model_id = settings.embedding_model
    revision = settings.embedding_model_revision
    identity = f"{model_id}@{revision}" if revision else model_id
    if len(identity) > _EMBEDDING_MODEL_MAX_CHARS:
        msg = (
            f"embedding identity {identity!r} is {len(identity)} characters; "
            f"ibex_core.memories.embedding_model accepts at most "
            f"{_EMBEDDING_MODEL_MAX_CHARS} (memories_embedding_model_len_chk). "
            "Shorten IBEX_MEMORY_EMBEDDING_MODEL or "
            "IBEX_MEMORY_EMBEDDING_MODEL_REVISION."
        )
        raise ValueError(msg)
    return identity
