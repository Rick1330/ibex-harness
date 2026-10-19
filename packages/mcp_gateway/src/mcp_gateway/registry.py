"""Versioned, inspectable tool registry with a canonical descriptor hash.

A ``ToolSpec`` is the single source of truth for a tool's declared capability,
typed scope, per-call bounds, and JSON-Schema descriptors. The registry only
admits read-only tools; a mutating tool cannot be registered (fail closed). The
descriptor hash binds the published tool surface to a stable digest so a change
is detectable, mirroring the ``pin descriptor hash to server identity/version``
requirement of ``mcp-gateway-policy.v1``.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from typing import Any

from pydantic import BaseModel

from mcp_gateway.scopes import Scope

READ_ONLY_ROLE = "read_only"

_MAX_TIMEOUT_MS = 30_000
_MAX_ROW_LIMIT = 1_000


def _validate_name(name: str) -> None:
    if not name or not name.strip():
        raise ValueError("tool name must be non-empty")
    if len(name) > 64:
        raise ValueError("tool name must be <= 64 characters")
    if any(ch.isspace() for ch in name):
        raise ValueError("tool name must not contain whitespace")


@dataclass(frozen=True, slots=True)
class ToolSpec:
    """Declared capability of a single read-only gateway tool."""

    name: str
    version: str
    scope: Scope
    description: str
    args_model: type[BaseModel]
    output_schema: Mapping[str, Any]
    timeout_ms: int
    row_limit: int
    role: str = READ_ONLY_ROLE

    def __post_init__(self) -> None:
        _validate_name(self.name)
        if not self.version:
            raise ValueError("tool version must be non-empty")
        if self.role != READ_ONLY_ROLE:
            raise ValueError(f"only {READ_ONLY_ROLE!r} tools may be registered")
        if not 1 <= int(self.timeout_ms) <= _MAX_TIMEOUT_MS:
            raise ValueError(f"timeout_ms must be in 1..{_MAX_TIMEOUT_MS}")
        if not 1 <= int(self.row_limit) <= _MAX_ROW_LIMIT:
            raise ValueError(f"row_limit must be in 1..{_MAX_ROW_LIMIT}")
        if not isinstance(self.args_model, type) or not issubclass(self.args_model, BaseModel):
            raise TypeError("args_model must be a pydantic BaseModel subclass")
        if not self.description:
            raise ValueError("tool description must be non-empty")

    @property
    def input_schema(self) -> dict[str, Any]:
        """JSON Schema for the tool arguments (``additionalProperties: false``)."""
        schema = self.args_model.model_json_schema()
        schema["additionalProperties"] = False
        return schema

    @property
    def timeout_seconds(self) -> float:
        return self.timeout_ms / 1000.0


@dataclass(frozen=True, slots=True)
class ToolDescriptor:
    """Canonical, hashable view of a tool for discovery and identity binding."""

    name: str
    version: str
    scope: str
    role: str
    description: str
    input_schema: Mapping[str, Any]
    output_schema: Mapping[str, Any]
    timeout_ms: int
    row_limit: int

    def as_mapping(self) -> dict[str, Any]:
        """Deterministic mapping used as the canonical descriptor bytes."""
        return {
            "name": self.name,
            "version": self.version,
            "scope": self.scope,
            "role": self.role,
            "description": self.description,
            "input_schema": _canonical(self.input_schema),
            "output_schema": _canonical(self.output_schema),
            "timeout_ms": self.timeout_ms,
            "row_limit": self.row_limit,
        }


def descriptor_for(spec: ToolSpec) -> ToolDescriptor:
    return ToolDescriptor(
        name=spec.name,
        version=spec.version,
        scope=spec.scope.value,
        role=spec.role,
        description=spec.description,
        input_schema=spec.input_schema,
        output_schema=spec.output_schema,
        timeout_ms=spec.timeout_ms,
        row_limit=spec.row_limit,
    )


def descriptor_hash(spec: ToolSpec) -> str:
    """SHA-256 over the canonical descriptor JSON (``sha256:<hex>``)."""
    payload = descriptor_for(spec).as_mapping()
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return "sha256:" + hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _canonical(value: Any) -> Any:
    """Recursively coerce mappings to plain dicts for deterministic hashing."""
    if isinstance(value, Mapping):
        return {str(key): _canonical(item) for key, item in sorted(value.items())}
    if isinstance(value, (list, tuple)):
        return [_canonical(item) for item in value]
    return value


class ToolRegistry:
    """Immutable-after-population registry of read-only tools."""

    def __init__(self, specs: Iterable[ToolSpec] = ()) -> None:
        self._specs: dict[str, ToolSpec] = {}
        for spec in specs:
            self.register(spec)

    def register(self, spec: ToolSpec) -> None:
        if spec.name in self._specs:
            raise ValueError(f"duplicate tool name {spec.name!r}")
        self._specs[spec.name] = spec

    def get(self, name: str) -> ToolSpec | None:
        return self._specs.get(name)

    def specs(self) -> tuple[ToolSpec, ...]:
        return tuple(self._specs[name] for name in sorted(self._specs))

    def descriptors(self) -> tuple[ToolDescriptor, ...]:
        return tuple(descriptor_for(spec) for spec in self.specs())

    def __len__(self) -> int:
        return len(self._specs)

    def __contains__(self, name: object) -> bool:
        return isinstance(name, str) and name in self._specs
