"""Unit tests for Settings PII knobs."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from app.config import Settings


def test_pii_defaults() -> None:
    settings = Settings()
    assert settings.pii_redact_min_confidence == pytest.approx(0.70)
    assert settings.pii_spacy_model == "en_core_web_md"
    assert settings.max_content_chars == 10_000


def test_pii_spacy_model_rejects_transformers() -> None:
    with pytest.raises(ValidationError):
        Settings(pii_spacy_model="en_core_web_trf")


def test_pii_spacy_model_rejects_unbundled_names() -> None:
    with pytest.raises(ValidationError):
        Settings(pii_spacy_model="en_core_web_lg")
    with pytest.raises(ValidationError):
        Settings(pii_spacy_model="not_a_real_model")


def test_pii_spacy_model_allows_bundled_md() -> None:
    settings = Settings(pii_spacy_model="en_core_web_md")
    assert settings.pii_spacy_model == "en_core_web_md"
