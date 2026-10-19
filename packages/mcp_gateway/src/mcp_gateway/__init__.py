"""Shared enforcement core for the read-only IBEX MCP operator gateway (GAP-009).

This package is transport-agnostic. It owns the authorization vocabulary and the
ordered enforcement pipeline; the deployable MCP surface lives in
``services/mcp-operator``. Nothing here performs I/O or imports an MCP SDK, so the
enforcement logic is unit-testable without a transport.
"""

from __future__ import annotations

from mcp_gateway.audit import (
    AsyncAuditEmitter,
    AuditEmitter,
    AuditSink,
    InMemoryAuditEmitter,
    NullAuditEmitter,
    ToolAuditEvent,
)
from mcp_gateway.enforcement import (
    GatewayEnforcer,
    RateLimiter,
    RateLimitOutcome,
    ToolContext,
    ToolExecutor,
)
from mcp_gateway.errors import (
    BackendUnavailableError,
    GatewayError,
    InvalidParamsError,
    NotFoundError,
    PermissionDeniedError,
    PolicyUnavailableError,
    RateLimitedError,
    RateLimitUnavailableError,
    ToolNotFoundError,
)
from mcp_gateway.policy import (
    BitmapPolicyEvaluator,
    PolicyDecision,
    PolicyEvaluator,
    PolicyResult,
)
from mcp_gateway.principal import GatewayPrincipal
from mcp_gateway.redaction import RedactionError, sanitize_output
from mcp_gateway.registry import (
    READ_ONLY_ROLE,
    ToolDescriptor,
    ToolRegistry,
    ToolSpec,
    descriptor_for,
    descriptor_hash,
)
from mcp_gateway.scopes import (
    SCOPE_PERMISSIONS,
    Scope,
    permission_for_scope,
    scope_granted,
)

__all__ = [
    "READ_ONLY_ROLE",
    "SCOPE_PERMISSIONS",
    "AsyncAuditEmitter",
    "AuditEmitter",
    "AuditSink",
    "BackendUnavailableError",
    "BitmapPolicyEvaluator",
    "GatewayEnforcer",
    "GatewayError",
    "GatewayPrincipal",
    "InMemoryAuditEmitter",
    "InvalidParamsError",
    "NotFoundError",
    "NullAuditEmitter",
    "PermissionDeniedError",
    "PolicyDecision",
    "PolicyEvaluator",
    "PolicyResult",
    "PolicyUnavailableError",
    "RateLimitOutcome",
    "RateLimitUnavailableError",
    "RateLimitedError",
    "RateLimiter",
    "RedactionError",
    "Scope",
    "ToolAuditEvent",
    "ToolContext",
    "ToolDescriptor",
    "ToolExecutor",
    "ToolNotFoundError",
    "ToolRegistry",
    "ToolSpec",
    "descriptor_for",
    "descriptor_hash",
    "permission_for_scope",
    "sanitize_output",
    "scope_granted",
]
