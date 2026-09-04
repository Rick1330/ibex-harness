"""Startup-once extraction provider registry (embedder BackendRegistry pattern)."""

from __future__ import annotations

from app.extraction.provider import ExtractionProvider


class UnknownExtractionProviderError(Exception):
    """Raised when EXTRACTION_PROVIDER is not openai or vllm."""


class ExtractionProviderRegistry:
    """Maps profile keys to ExtractionProvider implementations. Read-only after init."""

    def __init__(self, by_name: dict[str, ExtractionProvider]) -> None:
        if not by_name:
            raise ValueError("extraction provider registry is empty")
        self._by_name = dict(by_name)

    def for_profile(self, profile: str) -> ExtractionProvider:
        key = profile.strip().lower()
        try:
            return self._by_name[key]
        except KeyError as exc:
            raise UnknownExtractionProviderError(
                f"unknown extraction provider: {profile!r}"
            ) from exc

    def profiles(self) -> list[str]:
        return sorted(self._by_name.keys())
