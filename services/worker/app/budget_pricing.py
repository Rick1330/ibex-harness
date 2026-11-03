"""Rate-card pricing and estimation helpers for the worker budget ledger.

Pure functions shared by admission and settlement: token heuristics,
rate-card matching, per-component cost ceiling, and the deterministic
reservation key / request fingerprint for extraction calls.

Kept separate from ``app.budget_ledger`` so the ledger module stays focused on
persistence and transaction semantics (and below the code-health size limit).
"""

from __future__ import annotations

import fnmatch
import hashlib
import json
from dataclasses import dataclass
from uuid import UUID

DEFAULT_OUTPUT_TOKENS = 4096
TOKENS_PER_MESSAGE = 4
BYTES_PER_TOKEN = 4
COMPLETENESS_COMPLETE = "complete"
COMPLETENESS_ESTIMATED = "estimated"


@dataclass(frozen=True, slots=True)
class _PriceRow:
    provider: str
    model_pattern: str
    input_cents_per_1k: int
    output_cents_per_1k: int


@dataclass(frozen=True, slots=True)
class _Card:
    version: str
    prices: tuple[_PriceRow, ...]


def budget_reservation_key(*, session_id: UUID, first_turn_index: int) -> str:
    """Deterministic reservation key for one extraction unit of a session."""
    return f"extraction:{session_id}:{first_turn_index}"


def fingerprint_extraction_call(
    *, provider: str, model: str, system_prompt: str, user_content: str
) -> str:
    """Stable sha256 over the extraction call inputs (conflict detection)."""
    canonical = json.dumps(
        {
            "contract": "budget-reservation.v1",
            "operation": "extraction",
            "provider": provider,
            "model": model,
            "system_prompt": system_prompt,
            "user_content": user_content,
        },
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    ).encode("utf-8")
    return hashlib.sha256(canonical).hexdigest()


def estimate_prompt_tokens(*, system_prompt: str, user_content: str) -> tuple[int, int]:
    """Heuristic (input, output) token estimate; provider max output is unknown."""
    input_tokens = (
        _heuristic_tokens(system_prompt)
        + TOKENS_PER_MESSAGE
        + _heuristic_tokens(user_content)
        + TOKENS_PER_MESSAGE
    )
    return input_tokens, DEFAULT_OUTPUT_TOKENS


def _heuristic_tokens(content: str) -> int:
    if not content:
        return 0
    return max(len(content), len(content.encode("utf-8")) // BYTES_PER_TOKEN)


def _match_price(prices: tuple[_PriceRow, ...], provider: str, model: str) -> _PriceRow | None:
    """First row whose provider equals (case-insensitive) and pattern globs.

    Uses ``fnmatch`` (shell-style) as the close Python equivalent of Go
    ``path.Match``; model IDs do not contain separators in practice.
    """
    prov = provider.strip().lower()
    mod = model.strip()
    for row in prices:
        if row.provider.strip().lower() != prov:
            continue
        pattern = row.model_pattern.strip()
        if not pattern:
            continue
        if fnmatch.fnmatchcase(mod, pattern):
            return row
    return None


def cost_from_rates(
    *,
    input_cents_per_1k: int,
    output_cents_per_1k: int,
    input_tokens: int,
    output_tokens: int,
) -> int | None:
    """Cost cents with per-component ceiling, mirroring billing.EstimateCost."""
    if input_tokens < 0 or output_tokens < 0:
        return None
    if input_cents_per_1k < 0 or output_cents_per_1k < 0:
        return None
    return _ceil_mul_div_1k(input_tokens, input_cents_per_1k) + _ceil_mul_div_1k(
        output_tokens, output_cents_per_1k
    )


def _estimate_cost(
    card: _Card, provider: str, model: str, input_tokens: int, output_tokens: int
) -> int | None:
    """Cost cents for the matched card row; None when unusable (fail closed)."""
    if not card.version:
        return None
    row = _match_price(card.prices, provider, model)
    if row is None:
        return None
    return cost_from_rates(
        input_cents_per_1k=row.input_cents_per_1k,
        output_cents_per_1k=row.output_cents_per_1k,
        input_tokens=input_tokens,
        output_tokens=output_tokens,
    )


def _ceil_mul_div_1k(tokens: int, cents_per_1k: int) -> int:
    if tokens == 0 or cents_per_1k == 0:
        return 0
    return (tokens * cents_per_1k + 999) // 1000
