"""HostedAPIBackend — OpenAI / Cohere HTTP embedding for the hosted profile."""

from __future__ import annotations

import numpy as np
from numpy.typing import NDArray

from app.backends.base import EmbeddingBackend
from app.errors import GeometryMismatchError
from app.hosted.client import HostedClient
from app.hosted.providers import HostedProvider
from app.profiles import Profile
from app.validate import l2_normalize_rows, validate_embed_input, validate_output_vectors


class HostedAPIBackend(EmbeddingBackend):
    """Production embedding backend for IBEX_EMBEDDING_PROFILE=hosted.

    Always L2-normalizes upstream vectors then validates via validate_output_vectors
    (OpenAI does not guarantee unit norm; Cohere float vectors are likewise re-checked).

    Supported geometry (must match org pgvector `embedding_dim`):

    OpenAI
      - text-embedding-3-large: default 3072; Matryoshka 1..3072 via IBEX_EMBEDDING_DIM
      - text-embedding-3-small: default 1536; Matryoshka 1..1536
      - text-embedding-ada-002: fixed 1536

    Cohere
      - embed-english-v3.0 / embed-multilingual-v3.0: 1024
      - embed-english-light-v3.0 / embed-multilingual-light-v3.0: 384

    Never logs API keys, input text, or raw vector values.
    """

    def __init__(
        self,
        client: HostedClient,
        *,
        provider: HostedProvider,
        model_id: str,
        dimensions: int,
    ) -> None:
        if provider not in {"openai", "cohere"}:
            raise GeometryMismatchError(
                f"HostedAPIBackend: unsupported provider {provider!r}"
            )
        if not model_id.strip():
            raise GeometryMismatchError("HostedAPIBackend: model_id must not be empty")
        if dimensions < 1:
            raise GeometryMismatchError(
                f"HostedAPIBackend: dimensions must be positive, got {dimensions}"
            )
        self._client = client
        self._provider = provider
        self._model_id = model_id.strip()
        self._dimensions = dimensions

    @property
    def name(self) -> str:
        return self._provider

    @property
    def model_id(self) -> str:
        return self._model_id

    @property
    def dimensions(self) -> int:
        return self._dimensions

    @property
    def profile(self) -> Profile:
        return "hosted"

    @property
    def provider(self) -> HostedProvider:
        return self._provider

    async def embed(self, texts: list[str]) -> NDArray[np.float32]:
        validate_embed_input(texts)
        vectors = await self._client.embed(texts)
        normalized = l2_normalize_rows(np.asarray(vectors, dtype=np.float32))
        validate_output_vectors(texts, normalized, self._dimensions)
        return normalized

    async def aclose(self) -> None:
        """Close the underlying HTTP client. Called on lifespan shutdown."""
        await self._client.aclose()
