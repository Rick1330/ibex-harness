"""Validation helper tests."""

from __future__ import annotations

import numpy as np
import pytest

from app.errors import (
    BatchTooLargeError,
    EmptyBatchError,
    GeometryMismatchError,
    InvalidVectorError,
    MissingBackendError,
    TextTooLongError,
)
from app.limits import MAX_BATCH_TEXTS, MAX_TEXT_BYTES
from app.stub import StubBackend
from app.validate import (
    l2_normalize_rows,
    validate_embed_input,
    validate_geometry,
    validate_output_vectors,
    vector_l2_norm,
)


def test_validate_geometry_ok_and_mismatch() -> None:
    stub = StubBackend.for_profile("cpu")
    validate_geometry(stub, 384, "all-MiniLM-L6-v2")
    with pytest.raises(MissingBackendError):
        validate_geometry(None, 384, "all-MiniLM-L6-v2")
    with pytest.raises(GeometryMismatchError):
        validate_geometry(stub, 1024, "all-MiniLM-L6-v2")


def test_validate_embed_input_edges() -> None:
    with pytest.raises(EmptyBatchError):
        validate_embed_input([])
    with pytest.raises(BatchTooLargeError):
        validate_embed_input(["x"] * (MAX_BATCH_TEXTS + 1))
    with pytest.raises(TextTooLongError):
        validate_embed_input(["a" * (MAX_TEXT_BYTES + 1)])


def test_validate_output_vectors_shape() -> None:
    with pytest.raises(InvalidVectorError):
        validate_output_vectors(["a"], np.zeros((0, 2), dtype=np.float32), 2)
    with pytest.raises(InvalidVectorError):
        validate_output_vectors(["a"], np.array([[1.0]], dtype=np.float32), 2)
    with pytest.raises(InvalidVectorError):
        validate_output_vectors(["a"], np.array([1.0, 0.0], dtype=np.float32), 2)
    with pytest.raises(InvalidVectorError):
        validate_output_vectors(["a"], np.array(1.0, dtype=np.float32), 2)
    unnormalized = np.array([[3.0, 4.0]], dtype=np.float32)
    with pytest.raises(InvalidVectorError):
        validate_output_vectors(["a"], unnormalized, 2)


def test_l2_normalize_rows_rejects_zero() -> None:
    with pytest.raises(InvalidVectorError):
        l2_normalize_rows(np.zeros((1, 3), dtype=np.float32))
    row = l2_normalize_rows(np.array([[3.0, 4.0]], dtype=np.float32))[0]
    assert vector_l2_norm(row) == pytest.approx(1.0, abs=1e-6)
