"""Tier-1 structured PII read-path guard (milestone 3.E.1 / ISO-3.1)."""

from __future__ import annotations

import logging
import re
from collections.abc import Sequence
from typing import TYPE_CHECKING
from uuid import UUID

from app.read.metrics import PII_RECONFIRM

if TYPE_CHECKING:
    from app.read.models import MemorySearchResult

logger = logging.getLogger(__name__)

_EMAIL_RE = re.compile(
    r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b",
)
_PHONE_RE = re.compile(
    r"(?<!\d)(?:\+?1[-.\s]?)?(?:\(\d{3}\)|\d{3})[-.\s]?\d{3}[-.\s]?\d{4}(?!\d)",
)
_SSN_RE = re.compile(r"\b\d{3}-\d{2}-\d{4}\b")
_CREDIT_CARD_RE = re.compile(r"\b(?:\d[ -]*?){13,19}\b")
_IPV4_RE = re.compile(
    r"\b(?:(?:25[0-5]|2[0-4]\d|[01]?\d\d?)\.){3}"
    r"(?:25[0-5]|2[0-4]\d|[01]?\d\d?)\b",
)

_TIER1_CHECKS: tuple[re.Pattern[str], ...] = (
    _EMAIL_RE,
    _PHONE_RE,
    _SSN_RE,
    _CREDIT_CARD_RE,
    _IPV4_RE,
)


def tier1_structured_pii_present(content: str) -> bool:
    """Return True when Tier-1 structured PII patterns are present (regex-only, no spaCy)."""
    # Always scan for raw structured PII. Placeholder-only content passes when no pattern matches.
    return any(pattern.search(content) for pattern in _TIER1_CHECKS)


def should_block_read_result(content: str) -> bool:
    """Fail-closed: block returning memory content with Tier-1 structured PII."""
    blocked = tier1_structured_pii_present(content)
    PII_RECONFIRM.labels(result="blocked" if blocked else "passed").inc()
    if blocked:
        logger.warning("read-path Tier-1 PII re-check blocked memory content")
    return blocked


def filter_pii_blocked_results(results: list[MemorySearchResult]) -> list[MemorySearchResult]:
    """Drop search/hot-cache hits that fail Tier-1 read-path PII re-check."""
    return [item for item in results if not should_block_read_result(item.content)]


class PiiReadGuard:
    """Evaluate the Tier-1 re-check at most once per memory per request.

    The read paths evaluate one candidate list, then widen it for a refill or an
    FTS merge. Re-running the guard over the wider list would count the same row
    twice in ``ibex_memory_read_pii_reconfirm_total`` and re-log the same blocked
    memory, so verdicts from the first evaluation are reused and only unseen
    rows are scanned.
    """

    def __init__(self) -> None:
        self._evaluated: set[UUID] = set()
        self._allowed: set[UUID] = set()

    def allow(self, results: Sequence[MemorySearchResult]) -> list[MemorySearchResult]:
        fresh = [item for item in results if item.id not in self._evaluated]
        if fresh:
            self._evaluated.update(item.id for item in fresh)
            self._allowed.update(item.id for item in filter_pii_blocked_results(fresh))
        return [item for item in results if item.id in self._allowed]
