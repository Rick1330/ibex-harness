"""Labeled token estimates for budget calculation (not exact tiktoken/HF counts).

See ADR-0067 and follow-up issue for exact HF/Qwen family counting.
"""

from __future__ import annotations

import math

from app.capability_catalog import TokenizerFamilyPolicy

ESTIMATE_CHARS_DIV_4 = "chars_div_4"
ESTIMATE_RUNES_DIV_3_5 = "runes_div_3_5"


def estimate_tokens(text: str, policy: TokenizerFamilyPolicy) -> tuple[int, str]:
    """Return ``(token_estimate, estimate_kind)`` for ``text`` under ``policy``."""
    kind = policy.estimate_kind
    if kind == ESTIMATE_RUNES_DIV_3_5:
        return _estimate_runes_div_3_5(text), kind
    if kind == ESTIMATE_CHARS_DIV_4:
        return _estimate_chars_div_4(text), kind
    raise ValueError(f"unsupported estimate_kind {kind!r}")


def _estimate_chars_div_4(text: str) -> int:
    """``ceil(char_count / 4)`` — labeled approximation for OpenAI-family budgets."""
    if not text:
        return 0
    return math.ceil(len(text) / 4)


def _estimate_runes_div_3_5(text: str) -> int:
    """Match ADR-0043 Claude estimate: ``(runes*2+6)//7`` (empty → 0)."""
    if not text:
        return 0
    runes = len(text)  # Python str length is Unicode code points ≈ Go rune count for BMP+
    return (runes * 2 + 6) // 7
