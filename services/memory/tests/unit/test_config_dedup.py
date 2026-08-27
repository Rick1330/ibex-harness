"""Settings knobs for m3.C.2 dedup."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from app.config import Settings


def test_dedup_defaults() -> None:
    s = Settings()
    assert s.dedup_exact_enabled is True
    assert s.near_duplicate_sim_threshold == 0.92
    assert s.near_duplicate_candidate_limit == 10


def test_near_threshold_bounds() -> None:
    with pytest.raises(ValidationError):
        Settings(near_duplicate_sim_threshold=1.5)
    with pytest.raises(ValidationError):
        Settings(near_duplicate_candidate_limit=0)
