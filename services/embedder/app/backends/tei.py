"""TEIBackend — wraps TeiClient for the gpu deployment profile."""

from __future__ import annotations

import logging

import numpy as np
from numpy.typing import NDArray

from app.backends.base import EmbeddingBackend
from app.errors import GeometryMismatchError
from app.profiles import Profile
from app.tei.client import TeiClient
from app.validate import validate_embed_input, validate_output_vectors

logger = logging.getLogger(__name__)


class TEIBackend(EmbeddingBackend):
    """Production embedding backend backed by a TEI sidecar (profile == gpu).

    Validates input before sending to TEI and re-validates output after
    receiving it (shape, finiteness, L2 norm). 'normalize: true' in the
    TEI request is defense-in-depth, not trust.

    Never logs text content or raw vector values.
    """

    def __init__(
        self,
        client: TeiClient,
        *,
        model_id: str,
        dimensions: int,
    ) -> None:
        if not model_id.strip():
            raise GeometryMismatchError("TEIBackend: model_id must not be empty")
        if dimensions < 1:
            raise GeometryMismatchError(f"TEIBackend: dimensions must be positive, got {dimensions}")
        self._client = client
        self._model_id = model_id.strip()
        self._dimensions = dimensions

    @property
    def name(self) -> str:
        return "tei"

    @property
    def model_id(self) -> str:
        return self._model_id

    @property
    def dimensions(self) -> int:
        return self._dimensions

    @property
    def profile(self) -> Profile:
        return "gpu"

    async def embed(self, texts: list[str]) -> NDArray[np.float32]:
        validate_embed_input(texts)
        vectors = await self._client.embed(texts)
        validate_output_vectors(texts, vectors, self._dimensions)
        return vectors

    async def aclose(self) -> None:
        """Close the underlying HTTP client. Called on lifespan shutdown."""
        await self._client.aclose()

    async def health(self, timeout_seconds: float | None = None) -> bool:
        """Delegate to TeiClient.health() for startup polling."""
        return await self._client.health(timeout_seconds=timeout_seconds)

    async def info(self):
        """Delegate to TeiClient.info() for startup geometry check."""
        return await self._client.info()

    def model_id_from_info(self, info) -> str | None:
        """Extract model_id from /info response dict."""
        return self._client.model_id_from_info(info)
