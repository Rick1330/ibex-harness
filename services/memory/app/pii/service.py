"""PII analyze → confidence route → typed redaction."""

from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING

from app.pii.engine import (
    build_analyzer,
    build_analyzer_async,
    build_anonymizer,
    typed_operator_config,
)
from app.pii.types import PiiFinding, PiiProcessResult

if TYPE_CHECKING:
    from presidio_analyzer import AnalyzerEngine
    from presidio_anonymizer import AnonymizerEngine

    from app.config import Settings


class PiiService:
    """Constructor-injected Presidio engines (testable without globals)."""

    def __init__(
        self,
        settings: Settings,
        *,
        analyzer: AnalyzerEngine | None = None,
        anonymizer: AnonymizerEngine | None = None,
    ) -> None:
        self._settings = settings
        self._analyzer = analyzer
        self._anonymizer = anonymizer
        self._operators = typed_operator_config()

    @property
    def analyzer(self) -> AnalyzerEngine:
        if self._analyzer is None:
            self._analyzer = build_analyzer(self._settings)
        return self._analyzer

    @property
    def anonymizer(self) -> AnonymizerEngine:
        if self._anonymizer is None:
            self._anonymizer = build_anonymizer()
        return self._anonymizer

    async def ensure_ready(self) -> None:
        """Warm analyzer/anonymizer off the event loop (first-write safe)."""
        if self._analyzer is None:
            self._analyzer = await build_analyzer_async(self._settings)
        if self._anonymizer is None:
            self._anonymizer = await asyncio.to_thread(build_anonymizer)

    def process(self, content: str) -> PiiProcessResult:
        results = self.analyzer.analyze(text=content, language="en")
        findings = [
            PiiFinding(
                entity_type=r.entity_type,
                start=r.start,
                end=r.end,
                score=float(r.score),
            )
            for r in results
        ]
        if not findings:
            return PiiProcessResult(content=content)

        threshold = self._settings.pii_redact_min_confidence
        low = [f for f in findings if f.score < threshold]
        high = [f for f in findings if f.score >= threshold]

        if low:
            # Never silently redact or allow low-confidence PII.
            return PiiProcessResult(
                findings=findings,
                content=content,
                pii_detected=True,
                pii_redacted=False,
                status="quarantined",
                quarantine_reason="pii_low_confidence",
            )

        anonymized = self.anonymizer.anonymize(
            text=content,
            analyzer_results=results,
            operators=self._operators,
        )
        return PiiProcessResult(
            findings=findings,
            content=anonymized.text,
            pii_detected=True,
            pii_redacted=bool(high),
            status="active",
            quarantine_reason=None,
        )

    async def process_async(self, content: str) -> PiiProcessResult:
        """Run sync Presidio analyze/redact on a worker thread (non-blocking loop)."""
        await self.ensure_ready()
        return await asyncio.to_thread(self.process, content)
