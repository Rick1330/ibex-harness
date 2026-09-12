"""Soft model_pattern normalization for management API (ADR-0075).

Full filepath.Match grammar is enforced by the Go proxy at policy load.
This module only strips, bounds length, and rejects patterns listed in the
shared golden reject corpus (packages/modelpolicy/testdata).
"""

from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path

_MAX_PATTERN_LEN = 256
_GOLDEN_PATH = (
    Path(__file__).resolve().parents[4]
    / "packages"
    / "modelpolicy"
    / "testdata"
    / "model_pattern_golden.json"
)


@lru_cache(maxsize=1)
def _golden_reject() -> frozenset[str]:
    raw = json.loads(_GOLDEN_PATH.read_text(encoding="utf-8"))
    return frozenset(str(p) for p in raw["reject"])


def normalize_model_pattern(pattern: str) -> str:
    """Strip, bound length, reject known-bad golden patterns."""
    normalized = pattern.strip()
    if not normalized:
        raise ValueError("model_pattern is required")
    if len(normalized) > _MAX_PATTERN_LEN:
        raise ValueError(f"model_pattern exceeds {_MAX_PATTERN_LEN} characters")
    if normalized in _golden_reject():
        raise ValueError("model_pattern has invalid glob syntax")
    return normalized
