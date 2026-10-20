"""Positive-list output sanitizer (defense in depth).

The declared output schema is the allowlist: keys the schema does not declare are
dropped before a result leaves the gateway. A small sensitive-name deny-list is
applied on top so that a schema mistake cannot leak raw content, prompts, tool
arguments, tokens, or secrets. Scalar values must match the declared JSON type,
and schema-required keys (including nested objects) must survive, so a result
fails closed rather than returning an incomplete or mis-shaped record silently.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping
from typing import Any

from mcp_gateway.errors import GatewayError


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

_SUPPORTED_TYPES = frozenset({"object", "array", "string", "integer", "number", "boolean", "null"})

_CHECKERS: dict[str, Callable[[Any], bool]] = {
    "object": lambda value: isinstance(value, Mapping),
    "array": lambda value: isinstance(value, (list, tuple)),
    "string": lambda value: isinstance(value, str),
    "integer": lambda value: isinstance(value, int) and not isinstance(value, bool),
    "number": lambda value: isinstance(value, (int, float)) and not isinstance(value, bool),
    "boolean": lambda value: isinstance(value, bool),
}


def sanitize_output(
    payload: Mapping[str, Any] | None, output_schema: Mapping[str, Any]
) -> dict[str, Any]:
    """Return a schema-shaped copy of ``payload`` with only allowlisted keys."""
    value = _sanitize_value(payload, output_schema)
    if not isinstance(value, dict):  # pragma: no cover - root schema is an object
        raise RedactionError("tool result was not an object")
    return value


def _sanitize_object(payload: Mapping[str, Any], schema: Mapping[str, Any]) -> dict[str, Any]:
    properties = _properties(schema)
    result: dict[str, Any] = {}
    for key, value in payload.items():
        key_str = str(key)
        prop_schema = properties.get(key_str)
        if key_str in SENSITIVE_KEYS or not isinstance(prop_schema, Mapping):
            continue
        result[key_str] = _sanitize_value(value, prop_schema)
    _require_keys(schema, result)
    return result


def _sanitize_array(value: list[Any] | tuple[Any, ...], schema: Mapping[str, Any]) -> list[Any]:
    item_schema = schema.get("items", {})
    if not isinstance(item_schema, Mapping):
        raise RedactionError("array schema is missing items")
    return [_sanitize_value(item, item_schema) for item in value]


def _sanitize_value(value: Any, schema: Mapping[str, Any]) -> Any:
    types = _schema_types(schema)
    if value is None:
        if "null" not in types:
            raise RedactionError("tool result field is null but not nullable")
        return None
    matched = _first_match(value, types)
    if matched == "object":
        return _sanitize_object(value, schema)
    if matched == "array":
        return _sanitize_array(value, schema)
    return value


def _first_match(value: Any, types: list[str]) -> str:
    for schema_type in types:
        check = _CHECKERS.get(schema_type)
        if check is not None and check(value):
            return schema_type
    raise RedactionError("tool result field has an unexpected type")


def _properties(schema: Mapping[str, Any]) -> Mapping[str, Any]:
    properties = schema.get("properties", {})
    if not isinstance(properties, Mapping):
        raise RedactionError("output schema is missing properties")
    return properties


def _require_keys(schema: Mapping[str, Any], result: Mapping[str, Any]) -> None:
    required = schema.get("required", [])
    if not isinstance(required, (list, tuple)):
        return
    missing = [str(key) for key in required if str(key) not in result]
    if missing:
        raise RedactionError(f"tool result missing required fields: {', '.join(sorted(missing))}")


def _schema_types(schema: Mapping[str, Any]) -> list[str]:
    raw = schema.get("type")
    if isinstance(raw, str):
        types = [raw]
    elif isinstance(raw, (list, tuple)):
        types = _type_list(raw)
    else:
        raise RedactionError("output schema field is missing a type")
    _require_supported_types(types)
    return types


def _type_list(raw: list[Any] | tuple[Any, ...]) -> list[str]:
    if not raw or any(not isinstance(item, str) for item in raw):
        raise RedactionError("output schema has an unsupported type shape")
    return list(raw)


def _require_supported_types(types: list[str]) -> None:
    if any(schema_type not in _SUPPORTED_TYPES for schema_type in types):
        raise RedactionError("output schema has an unsupported type")
