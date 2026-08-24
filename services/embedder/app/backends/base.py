"""EmbeddingBackend ABC — async; mirrors packages/embedder.Embedder."""

from __future__ import annotations

from abc import ABC, abstractmethod

import numpy as np
from numpy.typing import NDArray

from app.profiles import Profile


class EmbeddingBackend(ABC):
    """Produces L2-normalized embedding vectors for text batches.

    Implementations must be safe for concurrent async use after construction.
    All vectors from a single embed call share the same model geometry.
    Timeouts and retries live on the HTTP client / settings layer, not here.
    """

    @abstractmethod
    async def embed(self, texts: list[str]) -> NDArray[np.float32]:
        """Return shape (len(texts), dimensions), L2-normalized per row."""

    @property
    @abstractmethod
    def name(self) -> str:
        """Backend identifier (e.g. stub, tei, openai, local)."""

    @property
    @abstractmethod
    def model_id(self) -> str:
        """Model identifier (e.g. BAAI/bge-m3)."""

    @property
    @abstractmethod
    def dimensions(self) -> int:
        """Embedding vector length for this backend."""

    @property
    @abstractmethod
    def profile(self) -> Profile:
        """Deployment profile this backend serves."""
