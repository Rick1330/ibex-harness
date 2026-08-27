"""Temporal-interval-aware conflict detection service (m3.C.3 / ADR-0056)."""

from __future__ import annotations

import asyncio
from collections.abc import Callable
from typing import TYPE_CHECKING

from app.conflict.classifier import ConflictClassifier, NoopConflictClassifier
from app.conflict.intervals import intervals_overlap
from app.conflict.subjects import extract_subject_key, subjects_match
from app.conflict.types import (
    CandidateMemory,
    ConflictDecision,
    ConflictEvaluation,
    ConflictOutcome,
    IncomingMemory,
)

if TYPE_CHECKING:
    from app.config import Settings

SubjectExtractor = Callable[[str], str]


def _is_sequential_supersede(*, same_subject: bool, newer: bool, overlap: bool) -> bool:
    """True when newer same-subject claim does not overlap the candidate interval."""
    if not same_subject:
        return False
    if not newer:
        return False
    return not overlap


class ConflictService:
    """Classify near-dup candidates: auto-supersede or escalate."""

    def __init__(
        self,
        settings: Settings,
        *,
        classifier: ConflictClassifier | None = None,
        subject_extractor: SubjectExtractor | None = None,
    ) -> None:
        self._settings = settings
        self._classifier = classifier or NoopConflictClassifier()
        self._extract = subject_extractor or (
            lambda text: extract_subject_key(
                text, model_name=settings.pii_spacy_model
            )
        )

    async def evaluate(
        self,
        incoming: IncomingMemory,
        candidates: list[CandidateMemory],
    ) -> ConflictEvaluation:
        decisions: list[ConflictDecision] = []
        llm_calls = 0
        # spaCy / model load is sync — keep the event loop free.
        incoming_subject = await asyncio.to_thread(self._extract, incoming.content)
        for candidate in candidates:
            decision, used_llm = await self._decide_one(
                incoming, incoming_subject, candidate
            )
            decisions.append(decision)
            if used_llm:
                llm_calls += 1
        return ConflictEvaluation(decisions=decisions, llm_calls=llm_calls)

    async def _decide_one(
        self,
        incoming: IncomingMemory,
        incoming_subject: str,
        candidate: CandidateMemory,
    ) -> tuple[ConflictDecision, bool]:
        cand_subject = await asyncio.to_thread(self._extract, candidate.content)
        subject_key = incoming_subject or cand_subject
        newer = incoming.interval.valid_from > candidate.interval.valid_from
        overlap = intervals_overlap(incoming.interval, candidate.interval)
        if _is_sequential_supersede(
            same_subject=subjects_match(incoming_subject, cand_subject),
            newer=newer,
            overlap=overlap,
        ):
            return (
                ConflictDecision(
                    candidate_id=candidate.memory_id,
                    outcome=ConflictOutcome.SUPERSEDES,
                    llm_call_made=False,
                    subject_key=subject_key,
                    notes="sequential_non_overlapping",
                ),
                False,
            )
        if overlap:
            return await self._escalate(
                incoming, candidate, subject_key, "interval_overlap"
            )
        return (
            ConflictDecision(
                candidate_id=candidate.memory_id,
                outcome=ConflictOutcome.NO_CONFLICT,
                llm_call_made=False,
                subject_key=subject_key,
                notes="non_overlapping_distinct_or_older",
            ),
            False,
        )

    async def escalate_pair(
        self,
        incoming: IncomingMemory,
        candidate: CandidateMemory,
        *,
        subject_key: str = "",
        reason: str = "escalate",
    ) -> ConflictDecision:
        """Public escalation seam (missing validity / forced overlap path)."""
        decision, _used = await self._escalate(
            incoming, candidate, subject_key, reason
        )
        return decision

    async def _escalate(
        self,
        incoming: IncomingMemory,
        candidate: CandidateMemory,
        subject_key: str,
        reason: str,
    ) -> tuple[ConflictDecision, bool]:
        outcome = await self._classifier.classify(incoming, candidate)
        if outcome == ConflictOutcome.SUPERSEDES:
            outcome = ConflictOutcome.ESCALATE_PENDING
        used_llm = self._classifier.invokes_llm
        return (
            ConflictDecision(
                candidate_id=candidate.memory_id,
                outcome=outcome,
                llm_call_made=used_llm,
                subject_key=subject_key,
                notes=reason,
            ),
            used_llm,
        )
