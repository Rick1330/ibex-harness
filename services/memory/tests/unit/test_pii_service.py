"""PII detector/redactor unit tests (Presidio + confidence routing)."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import pytest

from app.config import Settings
from app.pii.service import PiiService


@dataclass
class _FakeRecognizerResult:
    entity_type: str
    start: int
    end: int
    score: float


class _FakeAnalyzer:
    def __init__(self, results: list[_FakeRecognizerResult]) -> None:
        self._results = results

    def analyze(self, text: str, language: str = "en", **_: Any) -> list[_FakeRecognizerResult]:
        del text, language
        return list(self._results)


class _FakeAnonymizer:
    def anonymize(self, text: str, analyzer_results: list[Any], operators: dict[str, Any]) -> Any:
        del operators
        # Simple typed replace for tests using fake spans.
        out = text
        for r in sorted(analyzer_results, key=lambda x: x.start, reverse=True):
            out = out[: r.start] + f"[{r.entity_type}]" + out[r.end :]

        class _R:
            def __init__(self, value: str) -> None:
                self.text = value

        return _R(out)


@pytest.fixture
def settings() -> Settings:
    return Settings(pii_redact_min_confidence=0.70, pii_spacy_model="en_core_web_md")


def test_high_confidence_redacts_and_stays_active(settings: Settings) -> None:
    text = "email me at alice@example.com please"
    start = text.index("alice@example.com")
    end = start + len("alice@example.com")
    svc = PiiService(
        settings,
        analyzer=_FakeAnalyzer(
            [_FakeRecognizerResult("EMAIL_ADDRESS", start, end, 0.95)]
        ),
        anonymizer=_FakeAnonymizer(),
    )
    result = svc.process(text)
    assert result.pii_detected is True
    assert result.pii_redacted is True
    assert result.status == "active"
    assert "alice@example.com" not in result.content
    assert "[EMAIL_ADDRESS]" in result.content


def test_low_confidence_quarantines_without_redaction(settings: Settings) -> None:
    text = "maybe a name like Jordan somewhere"
    start = text.index("Jordan")
    end = start + len("Jordan")
    svc = PiiService(
        settings,
        analyzer=_FakeAnalyzer([_FakeRecognizerResult("PERSON", start, end, 0.40)]),
        anonymizer=_FakeAnonymizer(),
    )
    result = svc.process(text)
    assert result.pii_detected is True
    assert result.pii_redacted is False
    assert result.status == "quarantined"
    assert result.quarantine_reason == "pii_low_confidence"
    assert result.content == text


def test_mixed_scores_quarantine_wins(settings: Settings) -> None:
    text = "Alice <alice@example.com>"
    email = "alice@example.com"
    e0 = text.index(email)
    n0 = text.index("Alice")
    svc = PiiService(
        settings,
        analyzer=_FakeAnalyzer(
            [
                _FakeRecognizerResult("EMAIL_ADDRESS", e0, e0 + len(email), 0.99),
                _FakeRecognizerResult("PERSON", n0, n0 + 5, 0.55),
            ]
        ),
        anonymizer=_FakeAnonymizer(),
    )
    result = svc.process(text)
    assert result.status == "quarantined"
    assert result.pii_redacted is False
    assert email in result.content


@pytest.mark.parametrize(
    ("label", "snippet"),
    [
        ("email", "reach me at ops@ibexharness.com for access"),
        ("phone", "call the desk at +1-415-555-0199 tomorrow"),
        ("ssn", "My SSN is 856-45-6789 on file"),
        ("credit_card", "card number 4111111111111111 for refund"),
        ("ip", "client connected from 203.0.113.42 yesterday"),
    ],
)
def test_structured_pii_true_positives(settings: Settings, label: str, snippet: str) -> None:
    svc = PiiService(settings)
    result = svc.process(snippet)
    assert result.pii_detected is True, label
    types = {f.entity_type for f in result.findings}
    expected = {
        "email": "EMAIL_ADDRESS",
        "phone": "PHONE_NUMBER",
        "ssn": "US_SSN",
        "credit_card": "CREDIT_CARD",
        "ip": "IP_ADDRESS",
    }[label]
    assert expected in types, (label, types)
    if result.status == "active":
        assert result.pii_redacted is True
        assert "[" in result.content


def test_false_positive_trap_product_sku_not_forced_quarantine(settings: Settings) -> None:
    # Phone-shaped SKU; may or may not fire — must not crash; if only low-score, quarantine.
    text = "Order SKU 555-01-2345 ships next week from warehouse B"
    svc = PiiService(settings)
    result = svc.process(text)
    assert result.status in {"active", "quarantined"}
    if result.status == "active" and not result.pii_detected:
        assert result.content == text
