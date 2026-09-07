"""Laplace-smoothed usefulness from positive/negative ledger counts."""

from __future__ import annotations

from decimal import ROUND_HALF_UP, Decimal


def laplace_usefulness(positive: int, negative: int) -> float:
    """Return (p+1)/(p+n+2) clamped to [0,1] and quantized to NUMERIC(3,2)."""
    if positive < 0 or negative < 0:
        msg = "positive and negative counts must be non-negative"
        raise ValueError(msg)
    raw = (positive + 1) / (positive + negative + 2)
    quantized = float(
        Decimal(str(raw)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    )
    return min(1.0, max(0.0, quantized))
