"""Soft model_pattern normalization for management API (ADR-0075).

Strips, bounds length, and rejects patterns Go filepath.Match would reject
(shared golden reject corpus + full grammar scan).
"""

from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path

from app.schemas.model_pattern_glob import go_filepath_match_error

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
    """Strip, bound length, reject invalid filepath.Match globs."""
    normalized = pattern.strip()
    _require_nonempty(normalized)
    _reject_too_long(normalized)
    _reject_invalid_glob(normalized)
    return normalized


def _require_nonempty(normalized: str) -> None:
    if not normalized:
        raise ValueError("model_pattern is required")


def _reject_too_long(normalized: str) -> None:
    if len(normalized) > _MAX_PATTERN_LEN:
        raise ValueError(f"model_pattern exceeds {_MAX_PATTERN_LEN} characters")


def _reject_invalid_glob(normalized: str) -> None:
    if normalized in _golden_reject():
        raise ValueError("model_pattern has invalid glob syntax")
    reason = go_filepath_match_error(normalized)
    if reason is not None:
        raise ValueError(f"model_pattern has invalid glob syntax ({reason})")
