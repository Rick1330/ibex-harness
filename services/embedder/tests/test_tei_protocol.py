"""Tests for TEI response parsers — native and OpenAI-compat formats."""

from __future__ import annotations

import numpy as np
import pytest

from app.errors import BackendRejectedError, InvalidVectorError
from app.tei.protocol import (
    parse_info_dimensions,
    parse_info_response,
    parse_native_embed_response,
    parse_openai_compat_embed_response,
)


class TestParseNativeEmbedResponse:
    def test_single_vector(self) -> None:
        body = [[0.1, 0.2, 0.3]]
        arr = parse_native_embed_response(body)
        assert arr.shape == (1, 3)
        assert arr.dtype == np.float32

    def test_batch_vectors(self) -> None:
        body = [[0.1, 0.2], [0.3, 0.4]]
        arr = parse_native_embed_response(body)
        assert arr.shape == (2, 2)

    def test_not_a_list_raises(self) -> None:
        with pytest.raises(InvalidVectorError, match="unexpected type"):
            parse_native_embed_response({"data": []})

    def test_dict_raises(self) -> None:
        with pytest.raises(InvalidVectorError):
            parse_native_embed_response({"inputs": [1, 2]})

    def test_non_numeric_values_raises(self) -> None:
        with pytest.raises(InvalidVectorError):
            parse_native_embed_response([["a", "b"]])

    def test_none_raises(self) -> None:
        with pytest.raises(InvalidVectorError):
            parse_native_embed_response(None)

    def test_empty_list_becomes_empty_array(self) -> None:
        arr = parse_native_embed_response([])
        assert arr.shape == (0,)

    def test_float32_dtype(self) -> None:
        body = [[1.0, 2.0, 3.0]]
        arr = parse_native_embed_response(body)
        assert arr.dtype == np.float32


class TestParseOpenAICompatEmbedResponse:
    def _make_body(self, embeddings: list[list[float]]) -> dict:
        return {
            "object": "list",
            "data": [
                {"object": "embedding", "embedding": emb, "index": i}
                for i, emb in enumerate(embeddings)
            ],
            "model": "BAAI/bge-m3",
        }

    def test_single_embedding(self) -> None:
        body = self._make_body([[0.1, 0.2, 0.3]])
        arr = parse_openai_compat_embed_response(body)
        assert arr.shape == (1, 3)
        assert arr.dtype == np.float32

    def test_batch_ordering_by_index(self) -> None:
        # Provide out-of-order data to confirm sorting by index.
        body = {
            "data": [
                {"embedding": [0.9, 0.9], "index": 1},
                {"embedding": [0.1, 0.1], "index": 0},
            ]
        }
        arr = parse_openai_compat_embed_response(body)
        assert arr[0, 0] == pytest.approx(0.1, abs=1e-6)
        assert arr[1, 0] == pytest.approx(0.9, abs=1e-6)

    def test_missing_data_key_raises(self) -> None:
        with pytest.raises(BackendRejectedError, match="missing 'data'"):
            parse_openai_compat_embed_response({"embeddings": []})

    def test_not_dict_raises(self) -> None:
        with pytest.raises(BackendRejectedError):
            parse_openai_compat_embed_response([[0.1, 0.2]])

    def test_empty_data_list_raises(self) -> None:
        with pytest.raises(BackendRejectedError, match="non-empty list"):
            parse_openai_compat_embed_response({"data": []})

    def test_missing_index_key_raises(self) -> None:
        body = {"data": [{"embedding": [1.0, 2.0]}]}
        with pytest.raises(InvalidVectorError, match="malformed"):
            parse_openai_compat_embed_response(body)

    def test_missing_embedding_key_raises(self) -> None:
        body = {"data": [{"index": 0}]}
        with pytest.raises(InvalidVectorError):
            parse_openai_compat_embed_response(body)

    def test_non_numeric_embedding_raises(self) -> None:
        body = {"data": [{"index": 0, "embedding": ["a", "b"]}]}
        with pytest.raises(InvalidVectorError):
            parse_openai_compat_embed_response(body)


class TestParseInfoResponse:
    def test_returns_model_id(self) -> None:
        assert parse_info_response({"model_id": "BAAI/bge-m3"}) == "BAAI/bge-m3"

    def test_returns_model_id_or_path(self) -> None:
        assert parse_info_response({"model_id_or_path": "BAAI/bge-m3"}) == "BAAI/bge-m3"

    def test_prefers_model_id_over_path(self) -> None:
        result = parse_info_response({"model_id": "a", "model_id_or_path": "b"})
        assert result == "a"

    def test_returns_none_if_absent(self) -> None:
        assert parse_info_response({}) is None

    def test_returns_none_for_non_dict(self) -> None:
        assert parse_info_response("not a dict") is None
        assert parse_info_response(None) is None
        assert parse_info_response([]) is None

    def test_empty_string_model_id_returns_none(self) -> None:
        assert parse_info_response({"model_id": ""}) is None


class TestParseInfoDimensions:
    def test_hidden_size(self) -> None:
        assert parse_info_dimensions({"hidden_size": 1024}) == 1024

    def test_dim_key(self) -> None:
        assert parse_info_dimensions({"dim": 384}) == 384

    def test_absent_or_invalid(self) -> None:
        assert parse_info_dimensions({}) is None
        assert parse_info_dimensions({"hidden_size": 0}) is None
        assert parse_info_dimensions({"hidden_size": "1024"}) is None
        assert parse_info_dimensions([]) is None
