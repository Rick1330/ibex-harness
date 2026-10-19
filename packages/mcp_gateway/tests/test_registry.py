"""Tool registry and descriptor-hash tests."""

from __future__ import annotations

from typing import Any

import pytest
from support import SAMPLE_OUTPUT_SCHEMA, SampleArgs

from mcp_gateway.registry import (
    READ_ONLY_ROLE,
    ToolRegistry,
    ToolSpec,
    descriptor_for,
    descriptor_hash,
)
from mcp_gateway.scopes import Scope


def _spec(**overrides: Any) -> ToolSpec:
    base: dict[str, Any] = {
        "name": "sample.get",
        "version": "v1",
        "scope": Scope.OPERATOR_READ,
        "description": "Sample read tool",
        "args_model": SampleArgs,
        "output_schema": SAMPLE_OUTPUT_SCHEMA,
        "timeout_ms": 1000,
        "row_limit": 50,
    }
    base.update(overrides)
    return ToolSpec(**base)


def test_register_get_and_sorted_specs() -> None:
    registry = ToolRegistry([_spec(name="b.get"), _spec(name="a.get")])
    assert [s.name for s in registry.specs()] == ["a.get", "b.get"]
    assert registry.get("a.get") is not None
    assert registry.get("missing") is None
    assert "a.get" in registry
    assert len(registry) == 2


def test_duplicate_name_rejected() -> None:
    registry = ToolRegistry([_spec()])
    with pytest.raises(ValueError, match="duplicate"):
        registry.register(_spec())


def test_only_read_only_role_allowed() -> None:
    with pytest.raises(ValueError, match="read_only"):
        _spec(role="write")


def test_bounds_enforced() -> None:
    with pytest.raises(ValueError, match="timeout_ms"):
        _spec(timeout_ms=0)
    with pytest.raises(ValueError, match="row_limit"):
        _spec(row_limit=10_000)


def test_invalid_args_model_type_rejected() -> None:
    with pytest.raises(TypeError):
        _spec(args_model=object)  # type: ignore[arg-type]


def test_input_schema_forbids_additional_properties() -> None:
    schema = _spec().input_schema
    assert schema["additionalProperties"] is False
    assert "resource_id" in schema["properties"]


def test_descriptor_hash_is_stable_and_binding() -> None:
    spec = _spec()
    assert descriptor_hash(spec) == descriptor_hash(_spec())
    assert descriptor_hash(spec).startswith("sha256:")
    assert descriptor_hash(spec) != descriptor_hash(_spec(version="v2"))
    assert descriptor_hash(spec) != descriptor_hash(_spec(timeout_ms=2000))
    assert descriptor_hash(spec) != descriptor_hash(_spec(row_limit=10))


def test_descriptor_view_exposes_contract_fields() -> None:
    descriptor = descriptor_for(_spec())
    mapping = descriptor.as_mapping()
    assert mapping["name"] == "sample.get"
    assert mapping["scope"] == "operator.read"
    assert mapping["role"] == READ_ONLY_ROLE
    assert mapping["timeout_ms"] == 1000
