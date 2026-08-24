"""Hosted provider geometry / defaults unit tests."""

from __future__ import annotations

import pytest

from app.errors import BackendUnavailableError, GeometryMismatchError
from app.hosted.providers import (
    normalize_hosted_provider,
    openai_request_dimensions,
    provider_defaults,
    resolve_hosted_geometry,
    valid_hosted_provider,
    validate_hosted_dimensions,
)


class TestProviderNormalize:
    def test_valid(self) -> None:
        assert valid_hosted_provider(" OpenAI ")
        assert not valid_hosted_provider("anthropic")

    def test_normalize(self) -> None:
        assert normalize_hosted_provider("COHERE") == "cohere"

    def test_normalize_unknown(self) -> None:
        with pytest.raises(ValueError, match="unknown hosted provider"):
            normalize_hosted_provider("anthropic")


class TestProviderDefaults:
    def test_openai(self) -> None:
        d = provider_defaults("openai")
        assert d.model_id == "text-embedding-3-large"
        assert d.dimensions == 3072

    def test_cohere(self) -> None:
        d = provider_defaults("cohere")
        assert d.model_id == "embed-english-v3.0"
        assert d.dimensions == 1024

    def test_voyage_fail_closed(self) -> None:
        with pytest.raises(BackendUnavailableError, match="not implemented"):
            provider_defaults("voyage")


class TestResolveGeometry:
    def test_openai_defaults(self) -> None:
        dim, model = resolve_hosted_geometry("openai", model=None, dim=None)
        assert dim == 3072
        assert model == "text-embedding-3-large"

    def test_openai_matryoshka_override(self) -> None:
        dim, model = resolve_hosted_geometry(
            "openai", model="text-embedding-3-large", dim=1024
        )
        assert dim == 1024
        assert model == "text-embedding-3-large"

    def test_openai_dim_too_large(self) -> None:
        with pytest.raises(GeometryMismatchError):
            resolve_hosted_geometry("openai", model="text-embedding-3-small", dim=2048)

    def test_cohere_fixed_dim(self) -> None:
        dim, model = resolve_hosted_geometry("cohere", model=None, dim=None)
        assert dim == 1024
        assert model == "embed-english-v3.0"

    def test_cohere_wrong_dim(self) -> None:
        with pytest.raises(GeometryMismatchError):
            resolve_hosted_geometry("cohere", model="embed-english-v3.0", dim=512)


class TestOpenAIRequestDimensions:
    def test_omit_at_default(self) -> None:
        assert openai_request_dimensions("text-embedding-3-large", 3072) is None

    def test_send_when_truncated(self) -> None:
        assert openai_request_dimensions("text-embedding-3-large", 256) == 256

    def test_ada_omits(self) -> None:
        assert openai_request_dimensions("text-embedding-ada-002", 1536) is None


class TestValidate:
    def test_openai_ada_default_dim(self) -> None:
        dim, model = resolve_hosted_geometry(
            "openai", model="text-embedding-ada-002", dim=None
        )
        assert dim == 1536
        assert model == "text-embedding-ada-002"

    def test_openai_unknown_model_uses_provider_default_dim(self) -> None:
        dim, model = resolve_hosted_geometry(
            "openai", model="text-embedding-custom", dim=None
        )
        assert dim == 3072
        assert model == "text-embedding-custom"

    def test_reject_non_positive_dim(self) -> None:
        with pytest.raises(GeometryMismatchError):
            validate_hosted_dimensions("openai", "text-embedding-3-large", 0)

    def test_ada_fixed(self) -> None:
        with pytest.raises(GeometryMismatchError):
            validate_hosted_dimensions("openai", "text-embedding-ada-002", 768)
