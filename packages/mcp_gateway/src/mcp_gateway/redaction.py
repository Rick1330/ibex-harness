"""Positive-list output sanitizer (defense in depth).

The declared output schema is the allowlist: keys the schema does not declare are
dropped before a result leaves the gateway. A small sensitive-name deny-list is
applied on top so that a schema mistake cannot leak raw content, prompts, tool
arguments, tokens, or secrets. Scalar values must match the declared JSON type,
and schema-required keys (including nested objects) must survive, so a result
fails closed rather than returning an incomplete or mis-shaped record silently.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from mcp_gateway.errors import GatewayError

_SCALAR_CHECKS: dict[str, Any] = {
    "string": lambda value: isinstance(value, str),
    "integer": lambda value: isinstance(value, int) and not isinstance(value, bool),
    "number": lambda value: isinstance(value, (int, float)) and not isinstance(value, bool),
    "boolean": lambda value: isinstance(value, bool),
}


class RedactionError(GatewayError):
    """Output could not be safely shaped for release (fail closed)."""

    code = "redaction_failed"
    http_status = 500

    def __init__(self, message: str = "output redaction failed") -> None:
        super().__init__(message)


# Never emitted even if a schema erroneously declares them.
SENSITIVE_KEYS: frozenset[str] = frozenset(
    {
        "content",
        "contents",
        "prompt",
        "prompts",
        "token",
        "tokens",
        "access_token",
        "secret",
        "secrets",
        "password",
        "api_key",
        "apikey",
        "authorization",
        "raw",
        "raw_content",
        "payload",
        "arguments",
        "args",
        "body",
        "messages",
        "message",
    }
)


def sanitize_output(
    payload: Mapping[str, Any] | None, output_schema: Mapping[str, Any]
) -> dict[str, Any]:
    """Return a schema-shaped copy of ``payload`` with only allowlisted keys."""
    value = _sanitize_value(payload, output_schema)
    if not isinstance(value, dict):  # pragma: no cover - root schema is an object
        raise RedactionError("tool result was not an object")
    return value


def _sanitize_object(payload: Mapping[str, Any], schema: Mapping[str, Any]) -> dict[str, Any]:
    properties = schema.get("properties", {})
    if not isinstance(properties, Mapping):
        raise RedactionError("output schema is missing properties")
    result: dict[str, Any] = {}
    for key, value in payload.items():
        key_str = str(key)
        if key_str in SENSITIVE_KEYS or key_str not in properties:
            continue
        prop_schema = properties[key_str]
        if not isinstance(prop_schema, Mapping):
            continue
        result[key_str] = _sanitize_value(value, prop_schema)
    required = schema.get("required", [])
    if isinstance(required, (list, tuple)):
        missing = [str(key) for key in required if str(key) not in result]
        if missing:
            raise RedactionError(
                f"tool result missing required fields: {', '.join(sorted(missing))}"
            )
    return result


def _sanitize_value(value: Any, schema: Mapping[str, Any]) -> Any:
    types = _schema_types(schema)
    if value is None:
        if "null" in types:
            return None
        raise RedactionError("tool result field is null but not nullable")
    if "object" in types:
        if not isinstance(value, Mapping):
            raise RedactionError("expected an object in tool result")
        return _sanitize_object(value, schema)
    if "array" in types:
        if not isinstance(value, (list, tuple)):
            raise RedactionError("expected an array in tool result")
        item_schema = schema.get("items", {})
        if not isinstance(item_schema, Mapping):
            raise RedactionError("array schema is missing items")
        return [_sanitize_value(item, item_schema) for item in value]
    for schema_type in types:
        check = _SCALAR_CHECKS.get(schema_type)
        if check is not None and check(value):
            return value
    raise RedactionError("tool result field has an unexpected type")


def _schema_types(schema: Mapping[str, Any]) -> list[str]:
    raw = schema.get("type")
    if isinstance(raw, str):
        return [raw]
    if isinstance(raw, (list, tuple)):
        return [item for item in raw if isinstance(item, str)]
    raise RedactionError("output schema field is missing a type")
