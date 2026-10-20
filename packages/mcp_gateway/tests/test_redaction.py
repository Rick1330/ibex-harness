"""Output sanitizer tests (positive allowlist + sensitive deny-list)."""

from __future__ import annotations

import pytest
from support import SAMPLE_OUTPUT_SCHEMA

from mcp_gateway.redaction import RedactionError, sanitize_output


def test_keeps_allowlisted_keys_and_drops_unknown() -> None:
    payload = {"resource_id": "r1", "status": "ok", "surprise": "leak"}
    result = sanitize_output(payload, SAMPLE_OUTPUT_SCHEMA)
    assert result == {"resource_id": "r1", "status": "ok"}


def test_drops_sensitive_keys_even_if_declared() -> None:
    payload = {
        "resource_id": "r1",
        "status": "ok",
        "detail": {"id": "d1", "content": "raw memory text"},
    }
    result = sanitize_output(payload, SAMPLE_OUTPUT_SCHEMA)
    assert result["detail"] == {"id": "d1"}


def test_filters_array_items() -> None:
    schema = {
        "type": "object",
        "required": ["tags"],
        "properties": {
            "tags": {
                "type": "array",
                "items": {"type": "object", "properties": {"name": {"type": "string"}}},
            }
        },
    }
    payload = {"tags": [{"name": "a", "content": "x"}, {"name": "b"}]}
    assert sanitize_output(payload, schema) == {"tags": [{"name": "a"}, {"name": "b"}]}


def test_missing_required_key_fails_closed() -> None:
    with pytest.raises(RedactionError, match="missing required"):
        sanitize_output({"resource_id": "r1"}, SAMPLE_OUTPUT_SCHEMA)


def test_non_object_result_fails_closed() -> None:
    with pytest.raises(RedactionError):
        sanitize_output(None, SAMPLE_OUTPUT_SCHEMA)
    with pytest.raises(RedactionError):
        sanitize_output([1, 2, 3], SAMPLE_OUTPUT_SCHEMA)  # type: ignore[arg-type]


def test_wrong_nested_type_fails_closed() -> None:
    with pytest.raises(RedactionError):
        sanitize_output(
            {"resource_id": "r1", "status": "ok", "detail": "not-an-object"},
            SAMPLE_OUTPUT_SCHEMA,
        )


def test_scalar_type_mismatch_fails_closed() -> None:
    with pytest.raises(RedactionError, match="unexpected type"):
        sanitize_output(
            {"resource_id": {"nested": "leak"}, "status": "ok"},
            SAMPLE_OUTPUT_SCHEMA,
        )


def test_non_nullable_scalar_rejects_null() -> None:
    with pytest.raises(RedactionError, match="not nullable"):
        sanitize_output({"resource_id": None, "status": "ok"}, SAMPLE_OUTPUT_SCHEMA)


def test_nested_required_key_fails_closed() -> None:
    schema = {
        "type": "object",
        "required": ["detail"],
        "properties": {
            "detail": {
                "type": "object",
                "required": ["id"],
                "properties": {"id": {"type": "string"}},
            }
        },
    }
    with pytest.raises(RedactionError, match="missing required"):
        sanitize_output({"detail": {}}, schema)


def test_unsupported_schema_type_fails_closed() -> None:
    schema = {
        "type": "object",
        "required": ["resource_id"],
        "properties": {"resource_id": {"type": "date"}},
    }
    with pytest.raises(RedactionError, match="unsupported type"):
        sanitize_output({"resource_id": "r1"}, schema)


def test_malformed_type_array_fails_closed() -> None:
    schema = {
        "type": "object",
        "required": ["resource_id"],
        "properties": {"resource_id": {"type": ["string", 1]}},
    }
    with pytest.raises(RedactionError, match="unsupported type shape"):
        sanitize_output({"resource_id": "r1"}, schema)


def test_nullable_type_array_accepts_supported_pair() -> None:
    schema = {
        "type": "object",
        "required": ["resource_id"],
        "properties": {"resource_id": {"type": ["string", "null"]}},
    }
    assert sanitize_output({"resource_id": "r1"}, schema) == {"resource_id": "r1"}
    assert sanitize_output({"resource_id": None}, schema) == {"resource_id": None}
