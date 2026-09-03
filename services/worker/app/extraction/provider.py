"""Extraction LLM provider ABC (m3.5.B.2 / ADR-0064).

Mirrors Go packages/provider: Name, SupportedModels, and a Complete-equivalent
extract() that returns body plus usage. Implementations must be safe after construction.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass


class ExtractionTransportError(Exception):
    """Transient provider HTTP failure eligible for IbexTask autoretry."""


class ExtractionProviderError(Exception):
    """Non-retryable provider configuration or response-shape error."""


@dataclass(frozen=True, slots=True)
class ExtractionCall:
    """Raw model output plus usage for llm_traces (never includes prompt text)."""

    raw_json: str
    model: str
    input_tokens: int
    output_tokens: int
    latency_ms: int


class ExtractionProvider(ABC):
    """Provider-agnostic extraction LLM client."""

    @abstractmethod
    def extract(self, system_prompt: str, user_content: str) -> ExtractionCall:
        """Return raw JSON string from the model. Caller validates/parses."""

    @property
    @abstractmethod
    def name(self) -> str:
        """Provider identifier (openai | vllm)."""

    @property
    @abstractmethod
    def supported_models(self) -> tuple[str, ...]:
        """Model IDs this provider is configured to call."""
