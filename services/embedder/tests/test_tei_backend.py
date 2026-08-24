"""Contract and error-mapping tests for TEIBackend."""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock

import numpy as np
import pytest

from app.backends.tei import TEIBackend
from app.errors import (
    BackendRejectedError,
    BackendUnavailableError,
    BatchTooLargeError,
    EmptyBatchError,
    GeometryMismatchError,
    InvalidVectorError,
    TextTooLongError,
)

_DIM = 1024
_MODEL = "BAAI/bge-m3"


def _l2_normalized_vectors(n: int, dim: int) -> np.ndarray:
    """Return n random L2-normalized float32 vectors."""
    rng = np.random.default_rng(42)
    raw = rng.standard_normal((n, dim)).astype(np.float32)
    norms = np.linalg.norm(raw, axis=1, keepdims=True)
    return (raw / norms).astype(np.float32)


def _make_backend(
    *,
    vectors: np.ndarray | None = None,
    model_id: str = _MODEL,
    dimensions: int = _DIM,
    side_effect: Exception | None = None,
) -> TEIBackend:
    """Build a TEIBackend with a mock TeiClient.

    When testing invalid constructor args pass model_id/dimensions directly
    and don't provide vectors (TEIBackend.__init__ will raise before any embed).
    """
    client = MagicMock()
    if side_effect is not None:
        client.embed = AsyncMock(side_effect=side_effect)
    else:
        # Only generate stub vectors when dimensions is valid.
        vecs = vectors if vectors is not None else (
            _l2_normalized_vectors(1, dimensions) if dimensions > 0 else np.empty((0,))
        )
        client.embed = AsyncMock(return_value=vecs)
    client.aclose = AsyncMock()
    client.health = AsyncMock(return_value=True)
    client.info = AsyncMock(return_value={"model_id": model_id})
    client.model_id_from_info = MagicMock(return_value=model_id)
    return TEIBackend(client, model_id=model_id, dimensions=dimensions)


class TestTEIBackendProperties:
    def test_name_is_tei(self) -> None:
        backend = _make_backend()
        assert backend.name == "tei"

    def test_profile_is_gpu(self) -> None:
        backend = _make_backend()
        assert backend.profile == "gpu"

    def test_model_id(self) -> None:
        backend = _make_backend()
        assert backend.model_id == _MODEL

    def test_dimensions(self) -> None:
        backend = _make_backend()
        assert backend.dimensions == _DIM

    def test_empty_model_id_raises(self) -> None:
        with pytest.raises(GeometryMismatchError):
            _make_backend(model_id="")

    def test_whitespace_model_id_raises(self) -> None:
        with pytest.raises(GeometryMismatchError):
            _make_backend(model_id="   ")

    def test_zero_dimensions_raises(self) -> None:
        with pytest.raises(GeometryMismatchError):
            _make_backend(dimensions=0)

    def test_negative_dimensions_raises(self) -> None:
        with pytest.raises(GeometryMismatchError):
            _make_backend(dimensions=-1)


class TestTEIBackendEmbed:
    async def test_single_text_returns_correct_shape(self) -> None:
        vecs = _l2_normalized_vectors(1, _DIM)
        backend = _make_backend(vectors=vecs)
        result = await backend.embed(["hello"])
        assert result.shape == (1, _DIM)
        assert result.dtype == np.float32

    async def test_batch_returns_correct_shape(self) -> None:
        vecs = _l2_normalized_vectors(3, _DIM)
        backend = _make_backend(vectors=vecs)
        result = await backend.embed(["a", "b", "c"])
        assert result.shape == (3, _DIM)

    async def test_output_is_l2_normalized(self) -> None:
        vecs = _l2_normalized_vectors(2, _DIM)
        backend = _make_backend(vectors=vecs)
        result = await backend.embed(["x", "y"])
        norms = np.linalg.norm(result, axis=1)
        np.testing.assert_allclose(norms, 1.0, atol=1e-5)

    async def test_deterministic_single_vs_batch(self) -> None:
        """Single text embed and batch embed with same text must produce equal vectors."""
        vecs_single = _l2_normalized_vectors(1, _DIM)
        vecs_batch = np.vstack([vecs_single, _l2_normalized_vectors(1, _DIM)])

        client = MagicMock()
        call_count = 0

        async def embed_fn(texts):
            nonlocal call_count
            if len(texts) == 1:
                return vecs_single
            return vecs_batch

        client.embed = embed_fn
        client.aclose = AsyncMock()
        backend = TEIBackend(client, model_id=_MODEL, dimensions=_DIM)

        single = await backend.embed(["hello"])
        batch = await backend.embed(["hello", "world"])
        np.testing.assert_array_equal(single[0], batch[0])

    async def test_empty_batch_raises(self) -> None:
        backend = _make_backend()
        with pytest.raises(EmptyBatchError):
            await backend.embed([])

    async def test_too_many_texts_raises(self) -> None:
        backend = _make_backend()
        with pytest.raises(BatchTooLargeError):
            await backend.embed(["x"] * 65)

    async def test_text_too_long_raises(self) -> None:
        backend = _make_backend()
        with pytest.raises(TextTooLongError):
            await backend.embed(["x" * (32 * 1024 + 1)])

    async def test_backend_unavailable_propagates(self) -> None:
        backend = _make_backend(side_effect=BackendUnavailableError("TEI down"))
        with pytest.raises(BackendUnavailableError):
            await backend.embed(["hello"])

    async def test_backend_rejected_propagates(self) -> None:
        backend = _make_backend(side_effect=BackendRejectedError("bad input"))
        with pytest.raises(BackendRejectedError):
            await backend.embed(["hello"])

    async def test_wrong_dim_in_response_raises_invalid_vector(self) -> None:
        wrong_vecs = _l2_normalized_vectors(1, 512)  # 512 ≠ 1024
        backend = _make_backend(vectors=wrong_vecs)
        with pytest.raises(InvalidVectorError):
            await backend.embed(["hello"])

    async def test_wrong_batch_count_raises_invalid_vector(self) -> None:
        wrong_vecs = _l2_normalized_vectors(2, _DIM)  # 2 vectors for 1 text
        backend = _make_backend(vectors=wrong_vecs)
        with pytest.raises(InvalidVectorError):
            await backend.embed(["single"])

    async def test_nan_in_response_raises_invalid_vector(self) -> None:
        vecs = _l2_normalized_vectors(1, _DIM)
        vecs[0, 0] = float("nan")
        backend = _make_backend(vectors=vecs)
        with pytest.raises(InvalidVectorError):
            await backend.embed(["hello"])

    async def test_unnormalized_response_raises_invalid_vector(self) -> None:
        raw = np.ones((1, _DIM), dtype=np.float32)  # norm = sqrt(dim) ≠ 1
        backend = _make_backend(vectors=raw)
        with pytest.raises(InvalidVectorError):
            await backend.embed(["hello"])

    async def test_rank1_response_raises_invalid_vector(self) -> None:
        rank1 = np.ones(_DIM, dtype=np.float32)
        backend = _make_backend(vectors=rank1)
        with pytest.raises(InvalidVectorError):
            await backend.embed(["hello"])

    async def test_scalar_response_raises_invalid_vector(self) -> None:
        scalar = np.float32(1.0)
        backend = _make_backend(vectors=scalar)
        with pytest.raises(InvalidVectorError):
            await backend.embed(["hello"])

    async def test_concurrent_embed_safe(self) -> None:
        """asyncio.gather concurrent embed must not panic or mix results."""
        vecs = _l2_normalized_vectors(1, _DIM)
        backend = _make_backend(vectors=vecs)
        results = await asyncio.gather(*[backend.embed(["x"]) for _ in range(16)])
        for r in results:
            assert r.shape == (1, _DIM)

    async def test_aclose_delegates_to_client(self) -> None:
        backend = _make_backend()
        await backend.aclose()
        backend._client.aclose.assert_called_once()

    async def test_health_delegates_to_client(self) -> None:
        backend = _make_backend()
        result = await backend.health()
        assert result is True
        backend._client.health.assert_called_once()

    async def test_info_delegates_to_client(self) -> None:
        backend = _make_backend()
        result = await backend.info()
        assert result == {"model_id": _MODEL}
        backend._client.info.assert_called_once()

    def test_model_id_from_info_delegates_to_client(self) -> None:
        backend = _make_backend()
        result = backend.model_id_from_info({"model_id": _MODEL})
        assert result == _MODEL


class TestTEINoTextOrVectorInLogs:
    async def test_embed_does_not_log_text(self, caplog) -> None:
        import logging
        vecs = _l2_normalized_vectors(1, _DIM)
        backend = _make_backend(vectors=vecs)
        secret_text = "super secret content xyz"
        with caplog.at_level(logging.DEBUG):
            await backend.embed([secret_text])
        for record in caplog.records:
            assert secret_text not in record.getMessage()
