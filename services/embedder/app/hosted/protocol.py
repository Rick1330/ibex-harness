"""Hosted provider response parsers.

OpenAI reuses the TEI OpenAI-compat parser (same JSON shape).
Cohere v1/v2 embed responses are isolated here for API churn.
"""

from __future__ import annotations

from typing import Any

import numpy as np
from numpy.typing import NDArray

from app.errors import BackendRejectedError, InvalidVectorError
from app.tei.protocol import parse_openai_compat_embed_response

# Re-export for hosted callers / tests.
parse_openai_embed_response = parse_openai_compat_embed_response


def parse_cohere_embed_response(body: Any) -> NDArray[np.float32]:
    """Parse Cohere embed response → float32 ndarray.

    Supports:
      - Legacy floats: {"embeddings": [[...], ...]}
      - By-type (v1/v2): {"embeddings": {"float": [[...], ...]}}
    """
    if not isinstance(body, dict) or "embeddings" not in body:
        raise BackendRejectedError("Cohere embed response missing 'embeddings' field")
    vectors = _require_nonempty_float_rows(body["embeddings"])
    try:
        return np.array(vectors, dtype=np.float32)
    except (ValueError, TypeError) as exc:
        raise InvalidVectorError(f"Cohere embed response is not numeric: {exc}") from exc


def _require_nonempty_float_rows(raw: Any) -> list[Any]:
    rows = _cohere_rows(raw)
    if not rows:
        raise BackendRejectedError("Cohere 'embeddings' must be a non-empty list")
    return rows


def _cohere_rows(raw: Any) -> list[Any]:
    if isinstance(raw, list):
        return raw
    if isinstance(raw, dict):
        floats = raw.get("float")
        return floats if isinstance(floats, list) else []
    raise BackendRejectedError(
        f"Cohere 'embeddings' has unexpected type {type(raw).__name__!r}"
    )
