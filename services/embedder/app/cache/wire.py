"""Little-endian float32 wire codec for Redis embedding values.

Wire format is intentional and versioned by the Redis key prefix (`embed:v1`):
each vector is exactly ``dimensions * 4`` bytes of IEEE-754 binary32 in
little-endian order. Never pickle. Corrupt / non-contract blobs are treated
as cache misses by the decorator.
"""

from __future__ import annotations

import numpy as np
from numpy.typing import NDArray

_FLOAT32_BYTES = 4
_WIRE_DTYPE = np.dtype("<f4")
_L2_ATOL = 1e-5


def encode_vector(vec: NDArray[np.floating]) -> bytes:
    """Serialize one embedding row to little-endian float32 bytes."""
    return np.asarray(vec, dtype=_WIRE_DTYPE).reshape(-1).tobytes()


def decode_vector(blob: bytes | None, *, dimensions: int) -> NDArray[np.float32] | None:
    """Decode a wire blob, or return None when length/shape cannot be trusted."""
    if blob is None:
        return None
    if len(blob) != dimensions * _FLOAT32_BYTES:
        return None
    decoded = np.frombuffer(blob, dtype=_WIRE_DTYPE)
    # Copy out of the Redis buffer, then promote to native float32 for math.
    return np.ascontiguousarray(decoded, dtype=np.float32)


def is_contract_vector(vec: NDArray[np.float32], *, dimensions: int) -> bool:
    """True iff vec matches the embedder output contract (shape, finite, unit L2).

    Kept allocation-light for the cache hit path — same rules as
    ``validate_output_vectors`` for a single row, without building a fake batch.
    """
    if vec.ndim != 1 or vec.shape[0] != dimensions:
        return False
    if not np.all(np.isfinite(vec)):
        return False
    # Squared-norm check avoids a sqrt on every hit.
    sq = float(np.dot(vec, vec))
    return abs(sq - 1.0) <= (2.0 * _L2_ATOL)  # |n^2-1| ≈ 2|n-1| near n=1
