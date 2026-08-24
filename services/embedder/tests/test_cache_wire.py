"""Unit tests for the little-endian float32 wire codec."""

from __future__ import annotations

import numpy as np

from app.cache.wire import decode_vector, encode_vector, is_contract_vector


def _unit(dim: int = 4) -> np.ndarray:
    raw = np.arange(1, dim + 1, dtype=np.float32)
    return (raw / np.linalg.norm(raw)).astype(np.float32)


class TestWireCodec:
    def test_round_trip_little_endian(self) -> None:
        vec = _unit()
        blob = encode_vector(vec)
        assert len(blob) == 4 * 4
        # Explicit little-endian layout on the wire.
        assert blob == np.asarray(vec, dtype=np.dtype("<f4")).tobytes()
        out = decode_vector(blob, dimensions=4)
        assert out is not None
        np.testing.assert_array_equal(out, vec)
        assert is_contract_vector(out, dimensions=4)

    def test_rejects_wrong_length(self) -> None:
        assert decode_vector(b"abc", dimensions=4) is None
        assert decode_vector(None, dimensions=4) is None

    def test_rejects_non_finite_and_non_unit(self) -> None:
        assert not is_contract_vector(np.full(4, np.nan, dtype=np.float32), dimensions=4)
        assert not is_contract_vector(np.ones(4, dtype=np.float32), dimensions=4)
        assert not is_contract_vector(_unit(3), dimensions=4)
