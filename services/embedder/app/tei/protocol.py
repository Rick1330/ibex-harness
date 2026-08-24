"""TEI HTTP response parsers — native and OpenAI-compat formats.

Reused by G4.M3 (hosted OpenAI/Cohere) without modification.
"""

from __future__ import annotations

from typing import Any

import numpy as np
from numpy.typing import NDArray

from app.errors import BackendRejectedError, InvalidVectorError


def parse_native_embed_response(body: Any) -> NDArray[np.float32]:
    """Parse TEI native POST /embed response: number[][] → float32 ndarray.

    TEI returns a raw JSON array (not an object wrapper), so body must be a list.
    Raises InvalidVectorError for unexpected types or non-numeric values.
    """
    if not isinstance(body, list):
        raise InvalidVectorError(
            f"TEI native /embed returned unexpected type {type(body).__name__!r}; expected list"
        )
    try:
        arr = np.array(body, dtype=np.float32)
    except (ValueError, TypeError) as exc:
        raise InvalidVectorError(f"TEI native /embed response is not numeric: {exc}") from exc
    return arr


def parse_openai_compat_embed_response(body: Any) -> NDArray[np.float32]:
    """Parse OpenAI-compat POST /v1/embeddings response → float32 ndarray.

    Expected shape: {"data": [{"embedding": [...], "index": N}, ...], ...}
    Sorted by index to guarantee order.
    """
    data = _openai_compat_data(body)
    try:
        arr = np.array(_openai_compat_vectors(data), dtype=np.float32)
    except (KeyError, TypeError, ValueError) as exc:
        raise InvalidVectorError(
            f"TEI OpenAI-compat response has malformed embedding entries: {exc}"
        ) from exc
    return arr


def _openai_compat_data(body: Any) -> list[Any]:
    if not isinstance(body, dict) or "data" not in body:
        raise BackendRejectedError(
            "TEI OpenAI-compat /v1/embeddings missing 'data' field"
        )
    data = body["data"]
    if not isinstance(data, list) or not data:
        raise BackendRejectedError(
            "TEI OpenAI-compat 'data' must be a non-empty list"
        )
    return data


def _openai_compat_vectors(data: list[Any]) -> list[Any]:
    sorted_data = sorted(data, key=lambda item: item["index"])
    return [item["embedding"] for item in sorted_data]


def parse_info_response(body: Any) -> str | None:
    """Extract model_id from TEI GET /info response.

    Returns None if the field is absent (caller must fail closed on gpu readiness).
    """
    if not isinstance(body, dict):
        return None
    return body.get("model_id") or body.get("model_id_or_path") or None


def parse_info_dimensions(body: Any) -> int | None:
    """Extract embedding dimensionality from TEI GET /info when the field exists.

    TEI /info is not guaranteed to include dim; callers must still probe /embed.
    """
    if not isinstance(body, dict):
        return None
    for key in ("dim", "embedding_size", "hidden_size"):
        value = body.get(key)
        if isinstance(value, int) and value > 0:
            return value
    return None
