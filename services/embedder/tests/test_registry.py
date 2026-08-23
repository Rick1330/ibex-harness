"""Registry construction and lookup tests."""

from __future__ import annotations

import pytest

from app.errors import DuplicateProfileError, MissingBackendError, UnknownProfileError
from app.registry import BackendRegistry
from app.stub import StubBackend


def test_registry_for_profile_and_rejects() -> None:
    cpu = StubBackend.for_profile("cpu")
    gpu = StubBackend.for_profile("gpu")
    reg = BackendRegistry({"cpu": cpu, "gpu": gpu})
    assert reg.profiles() == ["cpu", "gpu"]

    got = reg.for_profile("cpu")
    assert got.name == "stub"
    assert got.dimensions == 384

    with pytest.raises(UnknownProfileError):
        reg.for_profile("hosted")

    with pytest.raises(UnknownProfileError):
        reg.for_profile("nope")


@pytest.mark.parametrize(
    ("profile", "backend", "expected"),
    [
        ("cpu", None, MissingBackendError),
        ("nope", StubBackend.for_profile("cpu"), UnknownProfileError),
        ("", StubBackend.for_profile("cpu"), UnknownProfileError),
        ("gpu", StubBackend.for_profile("cpu"), UnknownProfileError),
    ],
)
def test_registry_construction_failures(profile, backend, expected) -> None:
    with pytest.raises(expected):
        BackendRegistry({profile: backend})


def test_registry_duplicate_profile() -> None:
    cpu = StubBackend.for_profile("cpu")
    dst: dict[str, StubBackend] = {}
    BackendRegistry._register_one(dst, "cpu", cpu)
    with pytest.raises(DuplicateProfileError):
        BackendRegistry._register_one(dst, "cpu", cpu)
