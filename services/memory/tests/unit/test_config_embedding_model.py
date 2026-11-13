"""Embedding identity configuration: the value recorded on stored vectors (W10.3).

The stored id was a hardcoded literal, so a deployment on another embedding profile
recorded a model it did not use. These tests pin the configuration surface that
replaced it: a validated model id, an optional revision, and the single resolver both
write-path writers use. The resolver returns the *stored identity* — ``id`` or
``id@revision`` — not just the id, because the revision has to reach the column for
two revisions of one model to stay distinguishable.
"""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from app.config import Settings, resolve_embedding_identity

_ENV_MODEL = "IBEX_MEMORY_EMBEDDING_MODEL"
_ENV_REVISION = "IBEX_MEMORY_EMBEDDING_MODEL_REVISION"


@pytest.fixture(autouse=True)
def _clear_identity_env(monkeypatch: pytest.MonkeyPatch) -> None:
    """Isolate the tests from an operator shell that already exports these."""
    monkeypatch.delenv(_ENV_MODEL, raising=False)
    monkeypatch.delenv(_ENV_REVISION, raising=False)


def _pin_settings(monkeypatch: pytest.MonkeyPatch, **overrides: str) -> None:
    monkeypatch.setattr("app.config.get_settings", lambda: Settings(**overrides))


# --------------------------------------------------------------------- configuration


def test_default_model_id_is_the_value_already_recorded() -> None:
    settings = Settings()
    assert settings.embedding_model == "bge-m3"


def test_revision_defaults_empty() -> None:
    """Empty means "this deployment does not distinguish revisions"."""
    assert Settings().embedding_model_revision == ""


def test_model_id_and_revision_read_from_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(_ENV_MODEL, "BAAI/bge-m3")
    monkeypatch.setenv(_ENV_REVISION, "sha256:6c1f0a")
    settings = Settings()
    assert settings.embedding_model == "BAAI/bge-m3"
    assert settings.embedding_model_revision == "sha256:6c1f0a"


@pytest.mark.parametrize("value", ["", "   ", "\t\n"])
def test_empty_model_id_is_refused_at_startup(
    monkeypatch: pytest.MonkeyPatch,
    value: str,
) -> None:
    monkeypatch.setenv(_ENV_MODEL, value)
    with pytest.raises(ValidationError, match="embedding_model must be non-empty"):
        Settings()


def test_oversized_model_id_is_refused_at_startup() -> None:
    """257 characters cannot be stored: memories_embedding_model_len_chk is <= 256."""
    with pytest.raises(ValidationError, match="at most 256"):
        Settings(embedding_model="m" * 257)


def test_model_id_at_the_column_limit_is_accepted() -> None:
    assert len(Settings(embedding_model="m" * 256).embedding_model) == 256


def test_model_id_is_trimmed() -> None:
    """The stored value and the fence must compare byte-identically."""
    assert Settings(embedding_model="  bge-m3  ").embedding_model == "bge-m3"


def test_oversized_revision_is_refused() -> None:
    with pytest.raises(ValidationError, match="at most 256"):
        Settings(embedding_model_revision="r" * 257)


def test_revision_is_trimmed() -> None:
    assert Settings(embedding_model_revision="  rev1 ").embedding_model_revision == "rev1"


# -------------------------------------------------------------------------- resolver


def test_resolver_without_a_revision_keeps_the_bare_id(monkeypatch: pytest.MonkeyPatch) -> None:
    """No revision configured must be byte-identical to the value already stored."""
    _pin_settings(monkeypatch, embedding_model="bge-m3")
    assert resolve_embedding_identity() == "bge-m3"


def test_resolver_appends_the_configured_revision(monkeypatch: pytest.MonkeyPatch) -> None:
    _pin_settings(monkeypatch, embedding_model="bge-m3", embedding_model_revision="r1")
    assert resolve_embedding_identity() == "bge-m3@r1"


def test_two_revisions_resolve_to_different_identities(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _pin_settings(monkeypatch, embedding_model="bge-m3", embedding_model_revision="r1")
    first = resolve_embedding_identity()
    _pin_settings(monkeypatch, embedding_model="bge-m3", embedding_model_revision="r2")
    assert first != resolve_embedding_identity()


def test_resolver_prefers_an_explicit_identity(monkeypatch: pytest.MonkeyPatch) -> None:
    _pin_settings(monkeypatch, embedding_model="cfg")
    assert resolve_embedding_identity("explicit-model") == "explicit-model"


def test_resolver_still_applies_the_configured_revision_to_an_explicit_id(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The explicit argument pins the model id; the revision is the deployment's."""
    _pin_settings(monkeypatch, embedding_model="cfg", embedding_model_revision="r1")
    assert resolve_embedding_identity("  pinned  ") == "pinned@r1"


def test_resolver_falls_back_to_configured_model(monkeypatch: pytest.MonkeyPatch) -> None:
    _pin_settings(monkeypatch, embedding_model="cfg-model")
    assert resolve_embedding_identity() == "cfg-model"
    assert resolve_embedding_identity("   ") == "cfg-model"


def test_resolver_strips_an_explicit_identity(monkeypatch: pytest.MonkeyPatch) -> None:
    _pin_settings(monkeypatch)
    assert resolve_embedding_identity("  pinned  ") == "pinned"


def test_resolver_refuses_an_oversized_explicit_id(monkeypatch: pytest.MonkeyPatch) -> None:
    """The column check applies to the explicit path, not only to Settings."""
    _pin_settings(monkeypatch)
    with pytest.raises(ValueError, match="accepts at most 256"):
        resolve_embedding_identity("m" * 257)


def test_resolver_refuses_an_explicit_id_that_overflows_with_the_revision(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """``m`` * 250 + ``@r1`` is 253; a longer id plus the revision exceeds the column."""
    _pin_settings(monkeypatch, embedding_model_revision="r1")
    assert resolve_embedding_identity("m" * 250) == f"{'m' * 250}@r1"
    with pytest.raises(ValueError, match="accepts at most 256"):
        resolve_embedding_identity("m" * 254)


def test_resolver_accepts_a_composite_at_the_column_limit(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """253 + ``@r1`` is exactly 256, the largest storable identity."""
    _pin_settings(monkeypatch, embedding_model_revision="r1")
    identity = resolve_embedding_identity("m" * 253)
    assert len(identity) == 256
