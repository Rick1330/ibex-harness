"""Tests for HostedAPIBackend — validation, L2 normalize, error passthrough."""

from __future__ import annotations

from dataclasses import dataclass
from unittest.mock import AsyncMock, MagicMock

import numpy as np
import pytest

from app.backends.hosted import HostedAPIBackend
from app.errors import (
    BackendUnavailableError,
    EmptyBatchError,
    GeometryMismatchError,
    InvalidVectorError,
)
from app.validate import vector_l2_norm

_DIM = 8


@dataclass(frozen=True, slots=True)
class _BackendSpec:
    provider: str = "openai"
    model_id: str = "text-embedding-3-large"
    dimensions: int = _DIM
    embed_return: np.ndarray | None = None
    embed_side_effect: Exception | None = None


def _raw_vectors(n: int, dim: int = _DIM) -> np.ndarray:
    rng = np.random.default_rng(42)
    return rng.normal(size=(n, dim)).astype(np.float32)


def _make_backend(spec: _BackendSpec | None = None) -> HostedAPIBackend:
    probe = spec or _BackendSpec()
    client = MagicMock()
    if probe.embed_side_effect is not None:
        client.embed = AsyncMock(side_effect=probe.embed_side_effect)
    else:
        vecs = (
            probe.embed_return
            if probe.embed_return is not None
            else _raw_vectors(1, probe.dimensions)
        )
        client.embed = AsyncMock(return_value=vecs)
    client.aclose = AsyncMock()
    return HostedAPIBackend(
        client,
        provider=probe.provider,  # type: ignore[arg-type]
        model_id=probe.model_id,
        dimensions=probe.dimensions,
    )


class TestConstruction:
    def test_rejects_empty_model(self) -> None:
        client = MagicMock()
        with pytest.raises(GeometryMismatchError):
            HostedAPIBackend(client, provider="openai", model_id="  ", dimensions=8)

    def test_rejects_bad_dim(self) -> None:
        client = MagicMock()
        with pytest.raises(GeometryMismatchError):
            HostedAPIBackend(client, provider="openai", model_id="m", dimensions=0)

    def test_rejects_voyage_provider(self) -> None:
        client = MagicMock()
        with pytest.raises(GeometryMismatchError):
            HostedAPIBackend(
                client, provider="voyage", model_id="m", dimensions=8  # type: ignore[arg-type]
            )

    def test_name_is_provider(self) -> None:
        backend = _make_backend(
            _BackendSpec(provider="cohere", model_id="embed-english-v3.0")
        )
        assert backend.name == "cohere"
        assert backend.profile == "hosted"


class TestEmbed:
    async def test_l2_normalizes_openai_raw_vectors(self) -> None:
        raw = np.array([[3.0, 4.0] + [0.0] * (_DIM - 2)], dtype=np.float32)
        backend = _make_backend(_BackendSpec(embed_return=raw))
        out = await backend.embed(["hello"])
        assert out.shape == (1, _DIM)
        assert vector_l2_norm(out[0]) == pytest.approx(1.0, abs=1e-5)

    async def test_batch(self) -> None:
        backend = _make_backend(_BackendSpec(embed_return=_raw_vectors(3)))
        out = await backend.embed(["a", "b", "c"])
        assert out.shape == (3, _DIM)

    async def test_empty_batch_raises(self) -> None:
        backend = _make_backend()
        with pytest.raises(EmptyBatchError):
            await backend.embed([])

    async def test_wrong_dim_raises(self) -> None:
        backend = _make_backend(
            _BackendSpec(dimensions=_DIM, embed_return=_raw_vectors(1, 4))
        )
        with pytest.raises(InvalidVectorError):
            await backend.embed(["x"])

    async def test_aclose_delegates(self) -> None:
        backend = _make_backend()
        await backend.aclose()
        backend._client.aclose.assert_awaited_once()

    async def test_zero_vector_rejected(self) -> None:
        backend = _make_backend(
            _BackendSpec(embed_return=np.zeros((1, _DIM), dtype=np.float32))
        )
        with pytest.raises(InvalidVectorError):
            await backend.embed(["x"])

    async def test_passthrough_unavailable(self) -> None:
        backend = _make_backend(
            _BackendSpec(
                embed_side_effect=BackendUnavailableError("upstream down", retryable=False)
            )
        )
        with pytest.raises(BackendUnavailableError, match="upstream down"):
            await backend.embed(["x"])
