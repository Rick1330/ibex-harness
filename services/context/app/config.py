"""Context assembly settings (milestones 3.5.C.2 / 3.5.C.4 / 3.5.C.5 / 3.5.C.6)."""

from __future__ import annotations

import math
from typing import Final

from pydantic import AliasChoices, Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

# Hard cap for AssembleContextRequest.options.max_memories (0 = unlimited).
MAX_ASSEMBLY_OPTION_MEMORIES: Final[int] = 100


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
    """Env-backed knobs for parallel retrieval and the gRPC assembly server.

    ``IBEX_CONTEXT_TIMEOUT`` is the historical outer retrieval budget (default
    45ms). ``IBEX_CONTEXT_DEADLINE_MS`` (default 40) is the server-side
    retrieval wall used by AssembleContext so pack/format keep headroom under
    the proxy's 45ms client timeout (ADR-0071). Effective retrieval wait is
    ``min(timeout_ms, deadline_ms)`` via ``retrieval_wall_ms`` — ParallelRetriever
    consumes that property (not ``timeout_ms`` alone), so a 40ms deadline still
    cancels slow branches when timeout remains 45ms.
    """

    model_config = SettingsConfigDict(extra="ignore")

    timeout_ms: float = Field(
        default=45.0,
        gt=0,
        allow_inf_nan=False,
        validation_alias=AliasChoices("IBEX_CONTEXT_TIMEOUT", "IBEX_CONTEXT_TIMEOUT_MS"),
    )
    deadline_ms: float = Field(
        default=40.0,
        gt=0,
        allow_inf_nan=False,
        validation_alias="IBEX_CONTEXT_DEADLINE_MS",
        description=(
            "Server-side retrieval wall for AssembleContext (ADR-0071). "
            "Effective outer wait is min(timeout_ms, deadline_ms)."
        ),
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
    grpc_addr: str = Field(
        default="127.0.0.1:9092",
        validation_alias="IBEX_CONTEXT_GRPC_ADDR",
        description=(
            "Bind address for ContextAssemblyService (host:port). "
            "Non-loopback binds log a WARNING until 3.5.D.1 auth (ADR-0071)."
        ),
    )
    packer_dp_cell_ceiling: int = Field(
        default=70 * 6251,
        ge=1,
        validation_alias="IBEX_CONTEXT_PACKER_DP_CELL_CEILING",
        description=(
            "If n * (buckets+1) exceeds this, ContextPacker falls back to greedy "
            "(ADR-0069)."
        ),
    )
    packer_max_consecutive_skips: int = Field(
        default=5,
        ge=0,
        validation_alias="IBEX_CONTEXT_PACKER_MAX_CONSECUTIVE_SKIPS",
        description="Greedy fallback consecutive-skip limit before stopping.",
    )
    formatter_nonce_bytes: int = Field(
        default=16,
        ge=1,
        le=64,
        validation_alias="IBEX_CONTEXT_FORMATTER_NONCE_BYTES",
        description=(
            "Byte length for secrets.token_urlsafe per-assembly nonce on memory "
            "delimiters (ADR-0070); allowed range 1..64."
        ),
    )

    @property
    def retrieval_wall_ms(self) -> float:
        """Effective outer parallel-retrieval deadline consumed by ParallelRetriever."""
        return min(self.timeout_ms, self.deadline_ms)

    @field_validator(
        "timeout_ms",
        "deadline_ms",
        "directive_timeout_ms",
        "hot_timeout_ms",
        "cold_timeout_ms",
        mode="before",
    )
    @classmethod
    def _coerce_timeout_ms(cls, value: object) -> float:
        return _parse_timeout_ms(value)
