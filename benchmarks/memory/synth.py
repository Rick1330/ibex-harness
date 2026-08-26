"""Deterministic synthetic vectors for HNSW benches (not crypto)."""

from __future__ import annotations

import math

# Sonar/Codacy: seeded PRNG is required for planted near-neighbor recall; not used for secrets.
import random  # nosec B311  # NOSONAR

DIM = 1024
ACTIVE_DIMS = 64
_BOOTSTRAP_RESAMPLES = 1000
_ZERO_EPS = 1e-15


def unit_vector(seed: int) -> list[float]:
    rng = random.Random(seed)  # nosec B311  # NOSONAR
    vec = [0.0] * DIM
    for _ in range(ACTIVE_DIMS):
        idx = rng.randrange(DIM)
        vec[idx] += rng.gauss(0.0, 1.0)
    norm = math.sqrt(sum(x * x for x in vec)) or 1.0
    return [x / norm for x in vec]


def perturb(base: list[float], *, noise: float = 0.005, seed: int = 0) -> list[float]:
    rng = random.Random(seed ^ 0xA5A5_5A5A)  # nosec B311  # NOSONAR
    out = list(base)
    for i, x in enumerate(out):
        if abs(x) > _ZERO_EPS:
            out[i] = x + noise * rng.gauss(0.0, 1.0)
    norm = math.sqrt(sum(x * x for x in out)) or 1.0
    return [x / norm for x in out]


def vec_literal(vec: list[float]) -> str:
    return "[" + ",".join(f"{v:.6g}" for v in vec) + "]"


def percentile(sorted_vals: list[float], pct: float) -> float:
    if not sorted_vals:
        return 0.0
    if len(sorted_vals) == 1:
        return sorted_vals[0]
    rank = (pct / 100.0) * (len(sorted_vals) - 1)
    lo = int(math.floor(rank))
    hi = int(math.ceil(rank))
    if lo == hi:
        return sorted_vals[lo]
    weight = rank - lo
    return sorted_vals[lo] * (1.0 - weight) + sorted_vals[hi] * weight


def bootstrap_p95_ci(
    samples: list[float], *, resamples: int = _BOOTSTRAP_RESAMPLES, seed: int = 42
) -> tuple[float, float]:
    if len(samples) < 2:
        p = percentile(sorted(samples), 95)
        return p, p
    rng = random.Random(seed)  # nosec B311  # NOSONAR
    n = len(samples)
    estimates: list[float] = []
    for _ in range(resamples):
        draw = [samples[rng.randrange(n)] for _ in range(n)]
        estimates.append(percentile(sorted(draw), 95))
    estimates.sort()
    lo_i = int(0.025 * (len(estimates) - 1))
    hi_i = int(0.975 * (len(estimates) - 1))
    return estimates[lo_i], estimates[hi_i]
