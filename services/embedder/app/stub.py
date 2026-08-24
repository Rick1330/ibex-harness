"""Deterministic L2-normalized stub backend for tests and local contract checks."""

from __future__ import annotations

import hashlib

import numpy as np
from numpy.typing import NDArray

from app.backend import EmbeddingBackend
from app.errors import GeometryMismatchError, UnknownProfileError
from app.profiles import Profile, default_geometry, valid_profile
from app.validate import l2_normalize_rows, validate_embed_input, validate_output_vectors


def _deterministic_seed(text: str) -> int:
    """Non-cryptographic seed for stub vectors (test/dev only; not for security)."""
    digest = hashlib.sha256(text.encode("utf-8")).digest()
    return int.from_bytes(digest[:8], "big")


class StubBackend(EmbeddingBackend):
    """Deterministic stub; not production inference (name == stub)."""

    def __init__(self, profile: Profile, model_id: str, dimensions: int) -> None:
        if not valid_profile(profile):
            raise UnknownProfileError(f"unknown embedding profile: {profile!r}")
        if dimensions < 1:
            raise GeometryMismatchError(f"dimensions {dimensions}")
        if not model_id.strip():
            raise GeometryMismatchError("empty model id")
        self._profile: Profile = profile  # type: ignore[assignment]
        self._model_id = model_id
        self._dimensions = dimensions

    @classmethod
    def for_profile(cls, profile: Profile) -> StubBackend:
        geo = default_geometry(profile)
        return cls(profile=profile, model_id=geo.model_id, dimensions=geo.dimensions)

    @property
    def name(self) -> str:
        return "stub"

    @property
    def model_id(self) -> str:
        return self._model_id

    @property
    def dimensions(self) -> int:
        return self._dimensions

    @property
    def profile(self) -> Profile:
        return self._profile

    def embed(self, texts: list[str]) -> NDArray[np.float32]:
        validate_embed_input(texts)
        rows = [self._vector_for(text) for text in texts]
        vectors = np.vstack(rows).astype(np.float32, copy=False)
        validate_output_vectors(texts, vectors, self._dimensions)
        return vectors

    def _vector_for(self, text: str) -> NDArray[np.float32]:
        seed = _deterministic_seed(text)
        vec = np.empty(self._dimensions, dtype=np.float32)
        golden = 0x9E3779B97F4A7C15
        for i in range(self._dimensions):
            mixed = seed ^ ((i + 1) * golden)
            vec[i] = float(int(mixed % 2001) - 1000) / 1000.0
        return l2_normalize_rows(vec.reshape(1, -1))[0]
