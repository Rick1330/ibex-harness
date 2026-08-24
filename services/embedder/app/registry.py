"""Profile-keyed backend registry (read-only after construction)."""

from __future__ import annotations

from app.backends.base import EmbeddingBackend
from app.errors import (
    DuplicateProfileError,
    MissingBackendError,
    UnknownProfileError,
)
from app.profiles import valid_profile


def _validate_profile_key(profile: str) -> str:
    key = profile.strip()
    if not key or not valid_profile(key):
        raise UnknownProfileError(f"unknown embedding profile: {profile!r}")
    return key


def _validate_backend_present(key: str, backend: EmbeddingBackend | None) -> EmbeddingBackend:
    if backend is None:
        raise MissingBackendError(f"nil backend for {key!r}")
    return backend


def _validate_backend_profile_match(key: str, backend: EmbeddingBackend) -> None:
    if backend.profile != key:
        raise UnknownProfileError(
            f"key {key!r} backend reports {backend.profile!r}"
        )


def _ensure_unique_profile(dst: dict[str, EmbeddingBackend], key: str) -> None:
    if key in dst:
        raise DuplicateProfileError(f"duplicate embedding profile: {key!r}")


class BackendRegistry:
    """Maps deployment profiles to EmbeddingBackend implementations."""

    def __init__(self, by_profile: dict[str, EmbeddingBackend]) -> None:
        registered: dict[str, EmbeddingBackend] = {}
        for profile, backend in by_profile.items():
            self._register_one(registered, profile, backend)
        self._by_profile = registered

    @staticmethod
    def _register_one(
        dst: dict[str, EmbeddingBackend],
        profile: str,
        backend: EmbeddingBackend | None,
    ) -> None:
        key = _validate_profile_key(profile)
        impl = _validate_backend_present(key, backend)
        _validate_backend_profile_match(key, impl)
        _ensure_unique_profile(dst, key)
        dst[key] = impl

    def for_profile(self, profile: str) -> EmbeddingBackend:
        key = profile.strip()
        try:
            return self._by_profile[key]
        except KeyError as exc:
            raise UnknownProfileError(f"unknown embedding profile: {key!r}") from exc

    def profiles(self) -> list[str]:
        return sorted(self._by_profile.keys())
