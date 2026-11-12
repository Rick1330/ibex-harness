"""Deterministic prompt-injection heuristic for the memory write path (W10.4)."""

from app.injection.classifier import (
    INJECTION_QUARANTINE_REASON,
    NO_RULE,
    RULES,
    InjectionRule,
    classify,
    normalize,
)

__all__ = [
    "INJECTION_QUARANTINE_REASON",
    "NO_RULE",
    "RULES",
    "InjectionRule",
    "classify",
    "normalize",
]
