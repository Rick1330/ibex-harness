"""Contract tests for stub backend (dim + L2 + determinism)."""

from __future__ import annotations

import threading

import numpy as np
import pytest

from app.errors import GeometryMismatchError, UnknownProfileError
from app.profiles import default_geometry
from app.stub import StubBackend
from app.validate import validate_geometry, vector_l2_norm


@pytest.mark.parametrize("profile", ["cpu", "gpu", "hosted"])
def test_stub_contract_dim_and_l2(profile: str) -> None:
    stub = StubBackend.for_profile(profile)  # type: ignore[arg-type]
    geo = default_geometry(profile)
    validate_geometry(stub, geo.dimensions, geo.model_id)

    vectors = stub.embed(["hello", "world"])
    assert vectors.shape == (2, geo.dimensions)
    for row in vectors:
        assert vector_l2_norm(row) == pytest.approx(1.0, abs=1e-5)

    again = stub.embed(["hello"])
    np.testing.assert_array_equal(vectors[0], again[0])


def test_stub_concurrent_embed() -> None:
    stub = StubBackend.for_profile("cpu")
    errors: list[BaseException] = []

    def worker(i: int) -> None:
        try:
            stub.embed([chr(ord("a") + (i % 26))])
        except BaseException as exc:  # noqa: BLE001 — collect thread failures
            errors.append(exc)

    threads = [threading.Thread(target=worker, args=(i,)) for i in range(32)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert not errors


def test_new_stub_invalid() -> None:
    with pytest.raises(UnknownProfileError):
        StubBackend(profile="bad", model_id="m", dimensions=8)  # type: ignore[arg-type]
    with pytest.raises(GeometryMismatchError):
        StubBackend(profile="cpu", model_id="m", dimensions=0)
    with pytest.raises(GeometryMismatchError):
        StubBackend(profile="cpu", model_id="", dimensions=8)
