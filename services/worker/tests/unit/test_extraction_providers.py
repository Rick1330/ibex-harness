"""Unit tests for OpenAI-compatible extraction HTTP adapters."""

from __future__ import annotations

import json

import httpx
import pytest

from app.config import Settings
from app.extraction.factory import build_extraction_provider, build_registry
from app.extraction.openai_compat import CompatEndpoint
from app.extraction.openai_provider import OpenAIExtractionProvider
from app.extraction.provider import ExtractionProviderError, ExtractionTransportError
from app.extraction.registry import ExtractionProviderRegistry, UnknownExtractionProviderError
from app.extraction.vllm_provider import VLLMExtractionProvider


def _completion(content: str, *, prompt: int = 11, completion: int = 7) -> dict:
    return {
        "model": "returned-model",
        "choices": [{"message": {"content": content}}],
        "usage": {"prompt_tokens": prompt, "completion_tokens": completion},
    }


def _openai(client: httpx.Client, *, api_key: str = "sk-test") -> OpenAIExtractionProvider:
    return OpenAIExtractionProvider(
        CompatEndpoint(
            base_url="https://api.openai.com/v1",
            model="gpt-4o-mini",
            api_key=api_key,
            timeout_seconds=60.0,
        ),
        client,
    )


def test_openai_extract_sends_bearer_and_parses_usage() -> None:
    captured: dict[str, object] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["url"] = str(request.url)
        captured["auth"] = request.headers.get("authorization")
        body = json.loads(request.content)
        captured["model"] = body["model"]
        return httpx.Response(200, json=_completion('{"turns":[]}'))

    client = httpx.Client(transport=httpx.MockTransport(handler))
    provider = _openai(client)
    call = provider.extract("sys", "user")
    assert captured["auth"] == "Bearer sk-test"
    assert captured["url"].endswith("/chat/completions")
    assert captured["model"] == "gpt-4o-mini"
    assert call.raw_json == '{"turns":[]}'
    assert call.input_tokens == 11
    assert call.output_tokens == 7
    assert provider.name == "openai"
    assert provider.supported_models == ("gpt-4o-mini",)


def test_vllm_omits_authorization_when_key_empty() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.headers.get("authorization") is None
        return httpx.Response(200, json=_completion('{"turns":[]}'))

    client = httpx.Client(transport=httpx.MockTransport(handler))
    provider = VLLMExtractionProvider(
        CompatEndpoint(
            base_url="http://127.0.0.1:8000/v1",
            model="Qwen2.5-14B-Instruct",
            api_key=None,
            timeout_seconds=120.0,
        ),
        client,
    )
    call = provider.extract("sys", "user")
    assert call.model == "returned-model"
    assert provider.name == "vllm"
    assert provider.supported_models == ("Qwen2.5-14B-Instruct",)


def test_retryable_status_raises_transport_error() -> None:
    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(503, json={"error": "busy"})

    client = httpx.Client(transport=httpx.MockTransport(handler))
    provider = _openai(client, api_key="sk")
    with pytest.raises(ExtractionTransportError, match="503"):
        provider.extract("s", "u")


def test_client_error_is_not_retryable() -> None:
    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(401, json={"error": "no"})

    client = httpx.Client(transport=httpx.MockTransport(handler))
    provider = _openai(client, api_key="sk")
    with pytest.raises(ExtractionProviderError, match="401"):
        provider.extract("s", "u")


def test_strips_markdown_fence() -> None:
    fenced = '```json\n{"turns":[]}\n```'

    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=_completion(fenced))

    client = httpx.Client(transport=httpx.MockTransport(handler))
    provider = _openai(client, api_key="sk")
    call = provider.extract("s", "u")
    assert call.raw_json == '{"turns":[]}'


def test_factory_openai_requires_key() -> None:
    settings = Settings(extraction_provider="openai", openai_api_key=None)
    with pytest.raises(ValueError, match="OPENAI_API_KEY"):
        build_extraction_provider(settings)


def test_factory_vllm_requires_base_url() -> None:
    settings = Settings(extraction_provider="vllm", extraction_vllm_base_url=None)
    with pytest.raises(ValueError, match="EXTRACTION_BASE_URL"):
        build_extraction_provider(settings)


def test_factory_unknown_profile() -> None:
    settings = Settings(extraction_provider="anthropic")
    with pytest.raises(ValueError, match="unknown extraction provider"):
        build_extraction_provider(settings)


def test_registry_for_profile() -> None:
    settings = Settings(
        extraction_provider="openai",
        openai_api_key="sk-live",  # type: ignore[arg-type]
    )
    registry = build_registry(settings)
    assert registry.for_profile("openai").name == "openai"
    assert registry.profiles() == ["openai"]
    with pytest.raises(UnknownExtractionProviderError):
        registry.for_profile("vllm")


def test_factory_builds_openai_and_vllm() -> None:
    openai = build_extraction_provider(
        Settings(extraction_provider="openai", openai_api_key="sk-test")
    )
    assert openai.name == "openai"
    openai.close()  # type: ignore[union-attr]
    vllm = build_extraction_provider(
        Settings(
            extraction_provider="vllm",
            extraction_vllm_base_url="http://127.0.0.1:8000/v1",
        )
    )
    assert vllm.name == "vllm"
    vllm.close()  # type: ignore[union-attr]
    with pytest.raises(ValueError, match="empty"):
        ExtractionProviderRegistry({})


def test_openai_rejects_empty_base_url() -> None:
    endpoint = _endpoint(base_url="  ", api_key="sk")
    with pytest.raises(ValueError, match="base_url"):
        OpenAIExtractionProvider(endpoint)


def test_openai_rejects_empty_api_key() -> None:
    endpoint = _endpoint(api_key="  ")
    with pytest.raises(ValueError, match="API key"):
        OpenAIExtractionProvider(endpoint)


def test_vllm_rejects_empty_base_url() -> None:
    endpoint = CompatEndpoint(
        base_url="",
        model="Qwen2.5-14B-Instruct",
        api_key=None,
        timeout_seconds=1.0,
    )
    with pytest.raises(ValueError, match="base_url"):
        VLLMExtractionProvider(endpoint)


def _endpoint(*, base_url: str = "https://api.openai.com/v1", api_key: str) -> CompatEndpoint:
    return CompatEndpoint(
        base_url=base_url,
        model="gpt-4o-mini",
        api_key=api_key,
        timeout_seconds=1.0,
    )


def _provider_with(handler) -> OpenAIExtractionProvider:
    return _openai(httpx.Client(transport=httpx.MockTransport(handler)))


def _timeout_handler(_request: httpx.Request) -> httpx.Response:
    raise httpx.ReadTimeout("slow")


def _connect_handler(_request: httpx.Request) -> httpx.Response:
    raise httpx.ConnectError("down")


@pytest.mark.parametrize(
    ("handler", "exc_type", "match"),
    [
        (_timeout_handler, ExtractionTransportError, "timeout"),
        (_connect_handler, ExtractionTransportError, "transport"),
        (
            lambda _r: httpx.Response(200, json=["not", "object"]),
            ExtractionProviderError,
            "non-object",
        ),
        (
            lambda _r: httpx.Response(200, json={"choices": []}),
            ExtractionProviderError,
            "choices",
        ),
        (
            lambda _r: httpx.Response(200, json={"choices": [{"message": None}]}),
            ExtractionProviderError,
            "message",
        ),
        (
            lambda _r: httpx.Response(200, json={"choices": ["bad"]}),
            ExtractionProviderError,
            "choice is not an object",
        ),
        (
            lambda _r: httpx.Response(200, json=_completion("   ")),
            ExtractionProviderError,
            "content empty",
        ),
        (
            lambda _r: httpx.Response(200, json=_completion("not-json")),
            ExtractionProviderError,
            "not JSON",
        ),
        (
            lambda _r: httpx.Response(
                200, text="{not-json", headers={"Content-Type": "application/json"}
            ),
            ExtractionProviderError,
            "invalid JSON",
        ),
    ],
)
def test_provider_error_paths(handler, exc_type: type[Exception], match: str) -> None:
    provider = _provider_with(handler)
    with pytest.raises(exc_type, match=match):
        provider.extract("s", "u")


def test_missing_usage_defaults_to_zero_tokens() -> None:
    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={"model": "m", "choices": [{"message": {"content": '{"turns":[]}'}}]},
        )

    call = _provider_with(handler).extract("s", "u")
    assert call.input_tokens == 0
    assert call.output_tokens == 0


def test_response_model_fallback_for_non_object() -> None:
    from app.extraction.openai_compat_parse import response_model

    assert response_model(["not-a-dict"], "fallback-model") == "fallback-model"


def test_load_active_extraction_provider(monkeypatch: pytest.MonkeyPatch) -> None:
    from app.extraction.factory import load_active_extraction_provider

    load_active_extraction_provider.cache_clear()
    monkeypatch.setattr(
        "app.extraction.factory.get_settings",
        lambda: Settings(extraction_provider="openai", openai_api_key="sk-live"),
    )
    provider = load_active_extraction_provider()
    assert provider.name == "openai"
    load_active_extraction_provider.cache_clear()
