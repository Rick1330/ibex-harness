"""Self-hosted vLLM extraction adapter (OpenAI-compatible, no key)."""

from __future__ import annotations

import httpx

from app.extraction.openai_compat import CompatEndpoint, post_chat_completion
from app.extraction.provider import ExtractionCall, ExtractionProvider

DEFAULT_VLLM_MODEL = "Qwen2.5-14B-Instruct"


class VLLMExtractionProvider(ExtractionProvider):
    """vLLM OpenAI-compatible endpoint; omits Authorization when key empty."""

    def __init__(
        self,
        endpoint: CompatEndpoint,
        client: httpx.Client | None = None,
    ) -> None:
        if not endpoint.base_url.strip():
            raise ValueError("vllm extraction requires a base_url")
        self._endpoint = endpoint
        self._client = client or httpx.Client()
        self._owns_client = client is None

    @property
    def name(self) -> str:
        return "vllm"

    @property
    def supported_models(self) -> tuple[str, ...]:
        return (self._endpoint.model,)

    def extract(self, system_prompt: str, user_content: str) -> ExtractionCall:
        return post_chat_completion(self._client, self._endpoint, (system_prompt, user_content))

    def close(self) -> None:
        if self._owns_client:
            self._client.close()
