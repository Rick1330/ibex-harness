"""Build the active ExtractionProvider from worker Settings (fail-closed)."""

from __future__ import annotations

from functools import lru_cache

from app.config import Settings, get_settings
from app.extraction.openai_compat import CompatEndpoint
from app.extraction.openai_provider import (
    DEFAULT_OPENAI_BASE_URL,
    DEFAULT_OPENAI_MODEL,
    OpenAIExtractionProvider,
)
from app.extraction.provider import ExtractionProvider
from app.extraction.registry import ExtractionProviderRegistry
from app.extraction.vllm_provider import DEFAULT_VLLM_MODEL, VLLMExtractionProvider

VALID_PROFILES = frozenset({"openai", "vllm"})


def build_extraction_provider(settings: Settings) -> ExtractionProvider:
    """Construct the provider for settings.extraction_provider. Never stubs."""
    profile = settings.extraction_provider.strip().lower()
    if profile == "openai":
        return _build_openai(settings)
    if profile == "vllm":
        return _build_vllm(settings)
    raise ValueError(f"unknown extraction provider: {settings.extraction_provider!r}")


def _build_openai(settings: Settings) -> OpenAIExtractionProvider:
    key = settings.openai_api_key
    if key is None or not key.get_secret_value().strip():
        raise ValueError("openai extraction requires OPENAI_API_KEY")
    return OpenAIExtractionProvider(
        CompatEndpoint(
            base_url=settings.extraction_openai_base_url or DEFAULT_OPENAI_BASE_URL,
            model=settings.extraction_openai_model or DEFAULT_OPENAI_MODEL,
            api_key=key.get_secret_value(),
            timeout_seconds=settings.extraction_timeout_seconds,
        )
    )


def _build_vllm(settings: Settings) -> VLLMExtractionProvider:
    base = settings.extraction_vllm_base_url
    if not base or not base.strip():
        raise ValueError(
            "vllm extraction requires IBEX_WORKER_EXTRACTION_BASE_URL "
            "or IBEX_WORKER_EXTRACTION_VLLM_BASE_URL"
        )
    vllm_key = settings.extraction_vllm_api_key
    return VLLMExtractionProvider(
        CompatEndpoint(
            base_url=base,
            model=settings.extraction_vllm_model or DEFAULT_VLLM_MODEL,
            api_key=vllm_key.get_secret_value() if vllm_key else None,
            timeout_seconds=settings.extraction_timeout_seconds,
        )
    )


@lru_cache
def load_active_extraction_provider() -> ExtractionProvider:
    return build_extraction_provider(get_settings())


def build_registry(settings: Settings) -> ExtractionProviderRegistry:
    """Registry containing only the active profile (startup-once)."""
    provider = build_extraction_provider(settings)
    return ExtractionProviderRegistry({provider.name: provider})
