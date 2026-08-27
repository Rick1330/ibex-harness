"""Pipeline ordering: embed never sees unredacted PII content."""

from __future__ import annotations

from dataclasses import dataclass
from uuid import uuid4

import pytest

from app.config import Settings
from app.pii.service import PiiService
from app.pipeline import EmbedStage, PiiStage, ValidateStage, WriteContext, WritePipeline


@pytest.mark.asyncio
async def test_validate_rejects_empty() -> None:
    settings = Settings()
    pipe = WritePipeline([ValidateStage(settings)])
    ctx = await pipe.run(WriteContext(org_id=uuid4(), content="   "))
    assert ctx.stop is True
    assert ctx.error == "content_empty"


@pytest.mark.asyncio
async def test_embed_receives_only_redacted_content() -> None:
    settings = Settings(pii_redact_min_confidence=0.70)
    pii = PiiService(settings)
    seen: list[str] = []

    async def embed(text: str) -> list[float]:
        seen.append(text)
        return [0.0] * 8

    pipe = WritePipeline(
        [
            ValidateStage(settings),
            PiiStage(pii),
            EmbedStage(embed),
        ]
    )
    raw = "Please email alice@example.com about the contract"
    ctx = await pipe.run(WriteContext(org_id=uuid4(), content=raw))
    assert ctx.pii_detected is True
    if ctx.status == "quarantined":
        assert seen == []
        assert ctx.embedding is None
    else:
        assert ctx.pii_redacted is True
        assert len(seen) == 1
        assert "alice@example.com" not in seen[0]
        assert ctx.embedding is not None


@pytest.mark.asyncio
async def test_quarantine_skips_embed_stage() -> None:
    settings = Settings(pii_redact_min_confidence=0.99)

    @dataclass
    class _FakeRecognizerResult:
        entity_type: str
        start: int
        end: int
        score: float

    class _FakeAnalyzer:
        def __init__(self, results: list[_FakeRecognizerResult]) -> None:
            self._results = results

        def analyze(self, text: str, language: str = "en", **_: object) -> list[_FakeRecognizerResult]:
            del text, language
            return list(self._results)

    class _FakeAnonymizer:
        def anonymize(
            self, text: str, analyzer_results: list[object], operators: dict[str, object]
        ) -> object:
            del analyzer_results, operators

            class _R:
                def __init__(self, value: str) -> None:
                    self.text = value

            return _R(text)

    text = "Contact Jordan for details"
    start = text.index("Jordan")
    pii = PiiService(
        settings,
        analyzer=_FakeAnalyzer(  # type: ignore[arg-type]
            [_FakeRecognizerResult("PERSON", start, start + 6, 0.50)]
        ),
        anonymizer=_FakeAnonymizer(),  # type: ignore[arg-type]
    )
    seen: list[str] = []

    async def embed(payload: str) -> list[float]:
        seen.append(payload)
        return [1.0]

    pipe = WritePipeline([ValidateStage(settings), PiiStage(pii), EmbedStage(embed)])
    ctx = await pipe.run(WriteContext(org_id=uuid4(), content=text))
    assert ctx.status == "quarantined"
    assert ctx.stop is True
    assert seen == []
    assert "Jordan" in ctx.content
