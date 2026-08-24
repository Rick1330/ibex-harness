"""Hosted provider catalog — defaults, base URLs, and supported dimensions.

Supported geometry (documented for operators / pgvector provisioning):

OpenAI
  - text-embedding-3-large: default 3072; Matryoshka via API `dimensions` (1..3072)
  - text-embedding-3-small: default 1536; Matryoshka via API `dimensions` (1..1536)
  - text-embedding-ada-002: fixed 1536 (no dimensions parameter)

Cohere
  - embed-english-v3.0: fixed 1024
  - embed-multilingual-v3.0: fixed 1024
  - embed-english-light-v3.0: fixed 384
  - embed-multilingual-light-v3.0: fixed 384

Voyage is accepted in settings but fail-closed until a client lands.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from app.errors import BackendUnavailableError, GeometryMismatchError

HostedProvider = Literal["openai", "cohere", "voyage"]

VALID_HOSTED_PROVIDERS: frozenset[str] = frozenset({"openai", "cohere", "voyage"})

DEFAULT_OPENAI_BASE_URL = "https://api.openai.com/v1"
DEFAULT_COHERE_BASE_URL = "https://api.cohere.com"

# Models that accept OpenAI Matryoshka `dimensions` (max dim per model).
_OPENAI_MATRYOSHKA_MAX: dict[str, int] = {
    "text-embedding-3-large": 3072,
    "text-embedding-3-small": 1536,
}

# Fixed-dimension Cohere models (no output_dimension for v3.0 family).
_COHERE_FIXED_DIM: dict[str, int] = {
    "embed-english-v3.0": 1024,
    "embed-multilingual-v3.0": 1024,
    "embed-english-light-v3.0": 384,
    "embed-multilingual-light-v3.0": 384,
}


@dataclass(frozen=True, slots=True)
class ProviderDefaults:
    model_id: str
    dimensions: int
    base_url: str


def valid_hosted_provider(value: str) -> bool:
    return value.strip().lower() in VALID_HOSTED_PROVIDERS


def normalize_hosted_provider(value: str) -> HostedProvider:
    key = value.strip().lower()
    if key not in VALID_HOSTED_PROVIDERS:
        raise ValueError(f"unknown hosted provider: {value!r}")
    return key  # type: ignore[return-value]


def provider_defaults(provider: HostedProvider) -> ProviderDefaults:
    if provider == "openai":
        return ProviderDefaults(
            model_id="text-embedding-3-large",
            dimensions=3072,
            base_url=DEFAULT_OPENAI_BASE_URL,
        )
    if provider == "cohere":
        return ProviderDefaults(
            model_id="embed-english-v3.0",
            dimensions=1024,
            base_url=DEFAULT_COHERE_BASE_URL,
        )
    raise BackendUnavailableError(
        "hosted provider 'voyage' is not implemented yet — "
        "use IBEX_EMBEDDING_HOSTED_PROVIDER=openai|cohere"
    )


def resolve_hosted_geometry(
    provider: HostedProvider,
    *,
    model: str | None,
    dim: int | None,
) -> tuple[int, str]:
    """Return (dimensions, model_id) for the hosted provider."""
    defaults = provider_defaults(provider)
    model_id = model.strip() if model and model.strip() else defaults.model_id
    dimensions = dim if dim is not None else _default_dim_for_model(provider, model_id, defaults)
    validate_hosted_dimensions(provider, model_id, dimensions)
    return dimensions, model_id


def _default_dim_for_model(
    provider: HostedProvider,
    model_id: str,
    defaults: ProviderDefaults,
) -> int:
    if provider == "openai":
        if model_id in _OPENAI_MATRYOSHKA_MAX:
            return _OPENAI_MATRYOSHKA_MAX[model_id]
        if model_id == "text-embedding-ada-002":
            return 1536
        return defaults.dimensions
    if provider == "cohere":
        return _COHERE_FIXED_DIM.get(model_id, defaults.dimensions)
    return defaults.dimensions


def validate_hosted_dimensions(provider: HostedProvider, model_id: str, dimensions: int) -> None:
    if dimensions < 1:
        raise GeometryMismatchError(f"hosted dimensions must be >= 1, got {dimensions}")
    if provider == "openai":
        _validate_openai_dimensions(model_id, dimensions)
        return
    if provider == "cohere":
        _validate_cohere_dimensions(model_id, dimensions)


def _validate_openai_dimensions(model_id: str, dimensions: int) -> None:
    max_dim = _OPENAI_MATRYOSHKA_MAX.get(model_id)
    if max_dim is not None and dimensions > max_dim:
        raise GeometryMismatchError(
            f"OpenAI model {model_id!r} supports dimensions 1..{max_dim}, got {dimensions}"
        )
    if model_id == "text-embedding-ada-002" and dimensions != 1536:
        raise GeometryMismatchError(
            "text-embedding-ada-002 has fixed dimensions=1536 (no Matryoshka)"
        )


def _validate_cohere_dimensions(model_id: str, dimensions: int) -> None:
    fixed = _COHERE_FIXED_DIM.get(model_id)
    if fixed is not None and dimensions != fixed:
        raise GeometryMismatchError(
            f"Cohere model {model_id!r} has fixed dimensions={fixed}, got {dimensions}"
        )


def openai_request_dimensions(model_id: str, dimensions: int) -> int | None:
    """Return API `dimensions` when Matryoshka applies; None otherwise."""
    max_dim = _OPENAI_MATRYOSHKA_MAX.get(model_id)
    if max_dim is None or dimensions == max_dim:
        return None
    return dimensions
