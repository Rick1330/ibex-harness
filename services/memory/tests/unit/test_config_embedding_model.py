"""Embedding identity configuration: the model id recorded on stored vectors (W10.3).

The stored id was a hardcoded literal, so a deployment on another embedding profile
recorded a model it did not use. These tests pin the configuration surface that
replaced it: a validated model id, an optional revision, and the single resolver both
write-path writers use.
"""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from app.config import Settings, resolve_embedding_model

_ENV_MODEL = "IBEX_MEMORY_EMBEDDING_MODEL"
_ENV_REVISION = "IBEX_MEMORY_EMBEDDING_MODEL_REVISION"


@pytest.fixture(autouse=True)
def _clear_identity_env(monkeypatch: pytest.MonkeyPatch) -> None:
    """Isolate the tests from an operator shell that already exports these."""
    monkeypatch.delenv(_ENV_MODEL, raising=False)
    monkeypatch.delenv(_ENV_REVISION, raising=False)


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


def test_resolver_prefers_an_explicit_identity(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("app.config.get_settings", lambda: Settings(embedding_model="cfg"))
    assert resolve_embedding_model("explicit-model") == "explicit-model"


def test_resolver_falls_back_to_configured_model(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("app.config.get_settings", lambda: Settings(embedding_model="cfg-model"))
    assert resolve_embedding_model() == "cfg-model"
    assert resolve_embedding_model("   ") == "cfg-model"


def test_resolver_strips_an_explicit_identity() -> None:
    assert resolve_embedding_model("  pinned  ") == "pinned"
