"""Ordered, deny-by-default enforcement pipeline for operator MCP tool calls.

Pipeline (each stage fails closed):

1. enforce the org rate limit (over -> ``rate_limited``; authority down -> fail closed)
2. resolve tool from the registry (unknown -> ``tool_not_found``)
3. evaluate policy (bitmap today; unavailable authority -> ``policy_unavailable``)
4. validate arguments against the tool's JSON Schema (malformed -> ``invalid_params``)
5. execute the read under the tool's per-call timeout (timeout -> ``backend_unavailable``)
6. redact/sanitize the result against the declared output schema
7. emit a metadata-only audit event (never blocks the read)

The tenant-scoped database session is opened by the caller and passed in
``ToolContext``; the core performs no I/O of its own.
"""

from __future__ import annotations

import asyncio
import time
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any, Protocol
from uuid import UUID, uuid4

from pydantic import ValidationError

from mcp_gateway.audit import AuditEmitter, NullAuditEmitter, ToolAuditEvent
from mcp_gateway.errors import (
    BackendUnavailableError,
    GatewayError,
    InvalidParamsError,
    PermissionDeniedError,
    PolicyUnavailableError,
    RateLimitedError,
    ToolNotFoundError,
)
from mcp_gateway.policy import BitmapPolicyEvaluator, PolicyDecision, PolicyEvaluator, PolicyResult
from mcp_gateway.principal import GatewayPrincipal
from mcp_gateway.redaction import sanitize_output
from mcp_gateway.registry import ToolRegistry, ToolSpec, descriptor_hash


@dataclass(frozen=True, slots=True)
class RateLimitOutcome:
    allowed: bool
    limit: int
    remaining: int
    reset_unix: int


class RateLimiter(Protocol):
    """Org-scoped rate-limit authority. Must raise to signal unavailability."""

    async def check(self, org_id: UUID) -> RateLimitOutcome: ...


@dataclass(frozen=True, slots=True)
class ToolContext:
    """Everything an executor needs; the tenant authority is ``principal.org_id``.

    The executor opens its own tenant-scoped database session from ``org_id`` so
    that a denied call never establishes a database connection.
    """

    principal: GatewayPrincipal
    spec: ToolSpec
    request_id: str
    trace_id: str | None = None

    @property
    def org_id(self) -> UUID:
        return self.principal.org_id

    @property
    def timeout_seconds(self) -> float:
        return self.spec.timeout_seconds


class ToolExecutor(Protocol):
    """Executes a tenant-scoped read. Receives validated, schema-shaped args."""

    async def __call__(self, ctx: ToolContext, args: Mapping[str, Any]) -> Mapping[str, Any]: ...


@dataclass(frozen=True, slots=True)
class _Invocation:
    principal: GatewayPrincipal
    tool_name: str
    args: Mapping[str, Any] | None
    request_id: str
    trace_id: str | None


@dataclass(frozen=True, slots=True)
class CallContext:
    request_id: str = ""
    trace_id: str | None = None


@dataclass(slots=True)
class _AuditState:
    spec: ToolSpec | None = None
    decision: str = PolicyDecision.DENY.value
    scope_ok: bool = False
    success: bool = False
    error_code: str = ""


@dataclass(frozen=True, slots=True)
class EnforcerOptions:
    policy: PolicyEvaluator | None = None
    rate_limiter: RateLimiter | None = None
    audit: AuditEmitter | None = None


class GatewayEnforcer:
    """Transport-agnostic enforcement pipeline."""

    def __init__(
        self,
        registry: ToolRegistry,
        executor: ToolExecutor,
        *,
        options: EnforcerOptions | None = None,
    ) -> None:
        opts = options or EnforcerOptions()
        self._registry = registry
        self._executor = executor
        self._policy = opts.policy or BitmapPolicyEvaluator()
        self._rate_limiter = opts.rate_limiter
        self._audit = opts.audit or NullAuditEmitter()

    @property
    def registry(self) -> ToolRegistry:
        return self._registry

    async def invoke(
        self,
        principal: GatewayPrincipal,
        tool_name: str,
        args: Mapping[str, Any] | None,
        *,
        call: CallContext | None = None,
    ) -> dict[str, Any]:
        context = call or CallContext()
        invocation = _Invocation(
            principal=principal,
            tool_name=tool_name,
            args=args,
            request_id=context.request_id or str(uuid4()),
            trace_id=context.trace_id,
        )
        return await self._invoke_with_audit(
            invocation,
            started=time.perf_counter(),
            audit=_AuditState(),
        )

    async def _invoke_with_audit(
        self,
        invocation: _Invocation,
        *,
        started: float,
        audit: _AuditState,
    ) -> dict[str, Any]:
        try:
            return await self._run_pipeline(invocation, audit)
        except TimeoutError as exc:
            audit.error_code = BackendUnavailableError.code
            raise BackendUnavailableError(f"tool {invocation.tool_name!r} timed out") from exc
        except GatewayError as exc:
            audit.error_code = exc.code
            raise
        except Exception:
            audit.error_code = "internal_error"
            raise
        finally:
            self._emit_audit(invocation.principal, invocation.request_id, started, audit)

    async def _run_pipeline(self, invocation: _Invocation, audit: _AuditState) -> dict[str, Any]:
        await self._enforce_rate_limit(invocation.principal)
        spec = self._require_spec(invocation.tool_name, audit)
        await self._authorize(invocation.principal, spec, audit)
        parsed = self._validate_args(spec, invocation.args)
        ctx = ToolContext(
            principal=invocation.principal,
            spec=spec,
            request_id=invocation.request_id,
            trace_id=invocation.trace_id,
        )
        raw = await self._execute(ctx, parsed)
        result = sanitize_output(raw, spec.output_schema)
        audit.success = True
        return result

    def _require_spec(self, tool_name: str, audit: _AuditState) -> ToolSpec:
        spec = self._registry.get(tool_name)
        if spec is None:
            raise ToolNotFoundError(f"unknown tool {tool_name!r}")
        audit.spec = spec
        return spec

    async def _authorize(
        self, principal: GatewayPrincipal, spec: ToolSpec, audit: _AuditState
    ) -> None:
        policy_result = await self._evaluate_policy(principal, spec)
        audit.decision = policy_result.decision.value
        audit.scope_ok = policy_result.scope_satisfied
        if not policy_result.allowed:
            raise PermissionDeniedError(policy_result.reason)

    async def _evaluate_policy(self, principal: GatewayPrincipal, spec: ToolSpec) -> PolicyResult:
        try:
            return await self._policy.evaluate(principal, spec)
        except GatewayError:
            raise
        except Exception as exc:
            raise PolicyUnavailableError("policy evaluation failed") from exc

    @staticmethod
    def _validate_args(spec: ToolSpec, args: Mapping[str, Any] | None) -> dict[str, Any]:
        try:
            model = spec.args_model.model_validate(dict(args or {}))
        except ValidationError as exc:
            raise InvalidParamsError(_first_validation_message(exc)) from exc
        return model.model_dump()

    async def _enforce_rate_limit(self, principal: GatewayPrincipal) -> None:
        if self._rate_limiter is None:
            return
        outcome = await self._rate_limiter.check(principal.org_id)
        if not outcome.allowed:
            raise RateLimitedError()

    async def _execute(self, ctx: ToolContext, args: Mapping[str, Any]) -> Mapping[str, Any]:
        return await asyncio.wait_for(self._executor(ctx, args), timeout=ctx.timeout_seconds)

    def _emit_audit(
        self, principal: GatewayPrincipal, request_id: str, started: float, audit: _AuditState
    ) -> None:
        latency_ms = int((time.perf_counter() - started) * 1000)
        spec = audit.spec
        self._audit.emit(
            ToolAuditEvent(
                request_id=request_id,
                org_id=principal.org_id,
                agent_id=principal.agent_id,
                principal_id=principal.principal_id,
                token_id=principal.token_id,
                tool_name=spec.name if spec is not None else "",
                tool_version=spec.version if spec is not None else "",
                descriptor_hash=descriptor_hash(spec) if spec is not None else "",
                scope=spec.scope.value if spec is not None else "",
                scope_ok=audit.scope_ok,
                decision=audit.decision,
                success=audit.success,
                error_code=audit.error_code,
                latency_ms=latency_ms,
            )
        )


def _first_validation_message(exc: ValidationError) -> str:
    errors = exc.errors()
    if not errors:
        return "invalid tool arguments"
    err = errors[0]
    loc = ".".join(str(part) for part in err.get("loc", ()))
    msg = err.get("msg", "invalid")
    return f"{loc}: {msg}" if loc else str(msg)
