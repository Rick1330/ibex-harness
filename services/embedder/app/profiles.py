"""Deployment profile catalog (ADR-0046)."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from app.errors import UnknownProfileError

Profile = Literal["cpu", "gpu", "hosted"]

VALID_PROFILES: frozenset[str] = frozenset({"cpu", "gpu", "hosted"})


@dataclass(frozen=True, slots=True)
class ProfileDefaults:
    model_id: str
    dimensions: int


def valid_profile(profile: str) -> bool:
    return profile.strip() in VALID_PROFILES


def default_geometry(profile: str) -> ProfileDefaults:
    key = profile.strip()
    if key == "cpu":
        return ProfileDefaults(model_id="all-MiniLM-L6-v2", dimensions=384)
    if key == "gpu":
        return ProfileDefaults(model_id="BAAI/bge-m3", dimensions=1024)
    if key == "hosted":
        return ProfileDefaults(
            model_id="text-embedding-3-large",
            dimensions=3072,
        )
    raise UnknownProfileError(f"unknown embedding profile: {profile!r}")
