"""Hosted OpenAI extraction adapter (gpt-4o-mini default)."""

from __future__ import annotations

import httpx

from app.extraction.openai_compat import CompatEndpoint, post_chat_completion
from app.extraction.provider import ExtractionCall, ExtractionProvider

DEFAULT_OPENAI_BASE_URL = "https://api.openai.com/v1"
DEFAULT_OPENAI_MODEL = "gpt-4o-mini"


class OpenAIExtractionProvider(ExtractionProvider):
    """OpenAI chat completions with Bearer auth (Go AuthBearerAlways)."""

    def __init__(
        self,
        endpoint: CompatEndpoint,
        client: httpx.Client | None = None,
    ) -> None:
        if not endpoint.base_url.strip():
            raise ValueError("openai extraction requires a base_url")
        if not endpoint.api_key or not endpoint.api_key.strip():
            raise ValueError("openai extraction requires an API key")
        self._endpoint = endpoint
        self._client = client or httpx.Client()
        self._owns_client = client is None

    @property
    def name(self) -> str:
        return "openai"

    @property
    def supported_models(self) -> tuple[str, ...]:
        return (self._endpoint.model,)

    def extract(self, system_prompt: str, user_content: str) -> ExtractionCall:
        return post_chat_completion(self._client, self._endpoint, (system_prompt, user_content))

    def close(self) -> None:
        if self._owns_client:
            self._client.close()
