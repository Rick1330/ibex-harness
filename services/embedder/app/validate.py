"""Geometry and batch validation helpers."""

from __future__ import annotations

import math

import numpy as np
from numpy.typing import NDArray

from app.backend import EmbeddingBackend
from app.errors import (
    BatchTooLargeError,
    EmptyBatchError,
    GeometryMismatchError,
    InvalidVectorError,
    MissingBackendError,
    TextTooLongError,
)
from app.limits import MAX_BATCH_TEXTS, MAX_TEXT_BYTES


def validate_geometry(backend: EmbeddingBackend | None, want_dim: int, want_model: str) -> None:
    if backend is None:
        raise MissingBackendError("nil backend")
    want_model = want_model.strip()
    if want_dim < 1 or not want_model:
        raise GeometryMismatchError(
            f"invalid expected geometry dim={want_dim} model={want_model!r}"
        )
    if backend.dimensions != want_dim:
        raise GeometryMismatchError(
            f"dimensions got {backend.dimensions} want {want_dim}"
        )
    if backend.model_id.strip() != want_model:
        raise GeometryMismatchError(
            f"model got {backend.model_id!r} want {want_model!r}"
        )


def _validate_batch_bounds(texts: list[str]) -> None:
    if not texts:
        raise EmptyBatchError("empty embedding batch")
    if len(texts) > MAX_BATCH_TEXTS:
        raise BatchTooLargeError(f"{len(texts)} > {MAX_BATCH_TEXTS}")


def _validate_text_at(index: int, text: str) -> None:
    if not text:
        raise EmptyBatchError(f"empty text at index {index}")
    encoded = text.encode("utf-8")
    if len(encoded) > MAX_TEXT_BYTES:
        raise TextTooLongError(
            f"index {index} has {len(encoded)} bytes (max {MAX_TEXT_BYTES})"
        )


def validate_embed_input(texts: list[str]) -> None:
    _validate_batch_bounds(texts)
    for i, text in enumerate(texts):
        _validate_text_at(i, text)


def validate_output_vectors(
    texts: list[str],
    vectors: NDArray[np.float32],
    dim: int,
) -> None:
    if vectors.shape[0] != len(texts):
        raise InvalidVectorError(
            f"got {vectors.shape[0]} vectors for {len(texts)} texts"
        )
    if vectors.ndim != 2 or vectors.shape[1] != dim:
        raise InvalidVectorError(
            f"expected shape ({len(texts)}, {dim}), got {vectors.shape}"
        )
    if not np.all(np.isfinite(vectors)):
        raise InvalidVectorError("non-finite values in output")


def l2_normalize_rows(vectors: NDArray[np.float32]) -> NDArray[np.float32]:
    """L2-normalize each row in place; zero rows raise InvalidVectorError."""
    if vectors.size == 0:
        return vectors
    norms = np.linalg.norm(vectors, axis=1, keepdims=True)
    if np.any(norms == 0) or not np.all(np.isfinite(norms)):
        raise InvalidVectorError("cannot L2-normalize zero/non-finite vector")
    return vectors / norms


def vector_l2_norm(row: NDArray[np.float32]) -> float:
    return float(math.sqrt(float(np.dot(row, row))))
