"""Model-aware token budget calculator (milestone 3.5.C.1 / ADR-0067)."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

from app.capability_catalog import CapabilityCatalog, default_catalog
from app.estimate import estimate_tokens

# Minimum usable tokens left for memories after reserves + prompt parts.
MIN_VIABLE_MEMORY_BUDGET = 256

_RESPONSE_RESERVE_FLOOR = 500
_RESPONSE_RESERVE_CAP = 4096
_RESPONSE_RESERVE_FRACTION = 0.15


@dataclass(frozen=True, slots=True)
class Message:
    role: str
    content: str


@dataclass(frozen=True, slots=True)
class TokenBudget:
    context_window: int
    response_reserve: int
    safety_buffer: int
    usable_budget: int
    directive_tokens: int
    messages_tokens: int
    is_constrained: bool
    estimate_kind: str


def _concat_messages(messages: Sequence[Message]) -> str:
    parts: list[str] = []
    for msg in messages:
        parts.append(f"{msg.role}: {msg.content}")
    return "\n".join(parts)


def _response_reserve(context_window: int, max_output_tokens: int) -> int:
    pct = int(context_window * _RESPONSE_RESERVE_FRACTION)
    return max(_RESPONSE_RESERVE_FLOOR, min(pct, max_output_tokens, _RESPONSE_RESERVE_CAP))


class BudgetCalculator:
    """Compute usable token budget from the generate-and-diff capability catalog."""

    def __init__(self, catalog: CapabilityCatalog | None = None) -> None:
        self._catalog = catalog if catalog is not None else default_catalog()

    def calculate(
        self,
        model: str,
        messages: Sequence[Message],
        directive: str,
    ) -> TokenBudget:
        cap = self._catalog.for_model(model)
        policy = self._catalog.family_policy(cap.tokenizer_family)
        directive_tokens, kind = estimate_tokens(directive, policy)
        messages_tokens, kind2 = estimate_tokens(_concat_messages(messages), policy)
        if kind2 != kind:
            raise RuntimeError("estimate_kind mismatch between directive and messages")
        response_reserve = _response_reserve(cap.context_window, cap.max_output_tokens)
        safety_buffer = int(cap.context_window * policy.safety_buffer_fraction)
        usable = (
            cap.context_window
            - response_reserve
            - safety_buffer
            - directive_tokens
            - messages_tokens
        )
        usable = max(usable, 0)
        return TokenBudget(
            context_window=cap.context_window,
            response_reserve=response_reserve,
            safety_buffer=safety_buffer,
            usable_budget=usable,
            directive_tokens=directive_tokens,
            messages_tokens=messages_tokens,
            is_constrained=usable < MIN_VIABLE_MEMORY_BUDGET,
            estimate_kind=kind,
        )
