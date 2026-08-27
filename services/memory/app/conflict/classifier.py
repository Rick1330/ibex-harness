"""Pluggable LLM / heuristic conflict classifier (ADR-0056 escalation seam)."""

from __future__ import annotations

from typing import Protocol

from app.conflict.types import CandidateMemory, ConflictOutcome, IncomingMemory


class ConflictClassifier(Protocol):
    @property
    def invokes_llm(self) -> bool:
        """True when classify() performs a real LLM call."""
        ...

    async def classify(
        self,
        incoming: IncomingMemory,
        candidate: CandidateMemory,
    ) -> ConflictOutcome:
        """Return contradicts | near_duplicate | unrelated (never supersedes)."""
        ...


class NoopConflictClassifier:
    """Default classifier: records escalation without calling an LLM.

    Returns ESCALATE_PENDING so write/API layers can enqueue work later.
    """

    @property
    def invokes_llm(self) -> bool:
        return False

    async def classify(
        self,
        incoming: IncomingMemory,
        candidate: CandidateMemory,
    ) -> ConflictOutcome:
        del incoming, candidate
        return ConflictOutcome.ESCALATE_PENDING
