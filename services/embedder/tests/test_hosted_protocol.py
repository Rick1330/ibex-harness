"""Hosted protocol parsers — OpenAI-compat re-export + Cohere shapes."""

from __future__ import annotations

import numpy as np
import pytest

from app.errors import BackendRejectedError, InvalidVectorError
from app.hosted.protocol import parse_cohere_embed_response, parse_openai_embed_response


class TestParseOpenAIEmbed:
    def test_sorted_by_index(self) -> None:
        body = {
            "data": [
                {"index": 1, "embedding": [0.0, 1.0]},
                {"index": 0, "embedding": [1.0, 0.0]},
            ]
        }
        arr = parse_openai_embed_response(body)
        assert arr.shape == (2, 2)
        assert arr[0, 0] == pytest.approx(1.0)
        assert arr[1, 1] == pytest.approx(1.0)

    def test_missing_data_rejected(self) -> None:
        with pytest.raises(BackendRejectedError):
            parse_openai_embed_response({"object": "list"})


class TestParseCohereEmbed:
    def test_legacy_float_list(self) -> None:
        body = {"embeddings": [[1.0, 0.0], [0.0, 1.0]]}
        arr = parse_cohere_embed_response(body)
        assert arr.shape == (2, 2)
        assert arr.dtype == np.float32

    def test_by_type_float(self) -> None:
        body = {"embeddings": {"float": [[0.5, 0.5], [1.0, 0.0]]}}
        arr = parse_cohere_embed_response(body)
        assert arr.shape == (2, 2)

    def test_missing_embeddings_rejected(self) -> None:
        with pytest.raises(BackendRejectedError):
            parse_cohere_embed_response({"id": "x"})

    def test_empty_list_rejected(self) -> None:
        with pytest.raises(BackendRejectedError):
            parse_cohere_embed_response({"embeddings": []})

    def test_empty_float_rejected(self) -> None:
        with pytest.raises(BackendRejectedError):
            parse_cohere_embed_response({"embeddings": {"float": []}})

    def test_non_numeric_invalid(self) -> None:
        with pytest.raises(InvalidVectorError):
            parse_cohere_embed_response({"embeddings": [["x", "y"]]})

    def test_wrong_type_rejected(self) -> None:
        with pytest.raises(BackendRejectedError):
            parse_cohere_embed_response({"embeddings": "nope"})
