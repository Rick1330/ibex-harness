"""Presidio AnalyzerEngine / AnonymizerEngine construction (lazy, injectable)."""

from __future__ import annotations

from typing import TYPE_CHECKING

from presidio_analyzer import AnalyzerEngine
from presidio_analyzer.nlp_engine import NlpEngineProvider
from presidio_anonymizer import AnonymizerEngine
from presidio_anonymizer.entities import OperatorConfig

if TYPE_CHECKING:
    from app.config import Settings

# Entity types we expect on the write path (Tier 1 structured + Tier 2 NER).
_TYPED_PLACEHOLDER_ENTITIES: tuple[str, ...] = (
    "EMAIL_ADDRESS",
    "PHONE_NUMBER",
    "US_SSN",
    "CREDIT_CARD",
    "IP_ADDRESS",
    "PERSON",
    "LOCATION",
    "DATE_TIME",
    "NRP",
    "URL",
    "IBAN_CODE",
    "US_DRIVER_LICENSE",
    "US_PASSPORT",
    "US_BANK_NUMBER",
    "CRYPTO",
    "MEDICAL_LICENSE",
)


def build_analyzer(settings: Settings) -> AnalyzerEngine:
    """Build AnalyzerEngine with the configured spaCy CNN model."""
    configuration = {
        "nlp_engine_name": "spacy",
        "models": [{"lang_code": "en", "model_name": settings.pii_spacy_model}],
    }
    provider = NlpEngineProvider(nlp_configuration=configuration)
    nlp_engine = provider.create_engine()
    return AnalyzerEngine(nlp_engine=nlp_engine, supported_languages=["en"])


def build_anonymizer() -> AnonymizerEngine:
    return AnonymizerEngine()


def typed_operator_config() -> dict[str, OperatorConfig]:
    """Replace each entity type with `[ENTITY_TYPE]` (not generic REDACTED)."""
    ops: dict[str, OperatorConfig] = {
        "DEFAULT": OperatorConfig("replace", {"new_value": "[REDACTED]"}),
    }
    for entity in _TYPED_PLACEHOLDER_ENTITIES:
        ops[entity] = OperatorConfig("replace", {"new_value": f"[{entity}]"})
    return ops
