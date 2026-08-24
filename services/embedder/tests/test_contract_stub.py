"""Contract tests for stub backend (dim + L2 + determinism + concurrency)."""

from __future__ import annotations

import asyncio

import numpy as np
import pytest

from app.backends.stub import StubBackend
from app.errors import GeometryMismatchError, UnknownProfileError
from app.profiles import default_geometry
from app.validate import validate_geometry, vector_l2_norm


@pytest.mark.parametrize("profile", ["cpu", "gpu", "hosted"])
async def test_stub_contract_dim_and_l2(profile: str) -> None:
    stub = StubBackend.for_profile(profile)  # type: ignore[arg-type]
    geo = default_geometry(profile)
    validate_geometry(stub, geo.dimensions, geo.model_id)

    vectors = await stub.embed(["hello", "world"])
    assert vectors.shape == (2, geo.dimensions)
    for row in vectors:
        assert vector_l2_norm(row) == pytest.approx(1.0, abs=1e-5)

    again = await stub.embed(["hello"])
    np.testing.assert_array_equal(vectors[0], again[0])


async def test_stub_concurrent_embed() -> None:
    stub = StubBackend.for_profile("cpu")

    async def worker(i: int) -> None:
        await stub.embed([chr(ord("a") + (i % 26))])

    # asyncio.gather propagates exceptions automatically.
    await asyncio.gather(*[worker(i) for i in range(32)])


def test_new_stub_invalid() -> None:
    with pytest.raises(UnknownProfileError):
        StubBackend(profile="bad", model_id="m", dimensions=8)  # type: ignore[arg-type]
    with pytest.raises(GeometryMismatchError):
        StubBackend(profile="cpu", model_id="m", dimensions=0)
    with pytest.raises(GeometryMismatchError):
        StubBackend(profile="cpu", model_id="", dimensions=8)


def assert_backend_contract(backend, dim: int) -> None:
    """Shared helper: verify backend reports correct geometry.

    Used by stub tests and TEI backend tests so M3 can import and reuse.
    """
    assert backend.dimensions == dim
    assert backend.model_id
    assert backend.name
    assert backend.profile in ("cpu", "gpu", "hosted")
